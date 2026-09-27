"""Publish the Raspberry Pi camera to MediaMTX as an H.264 RTSP stream."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse
import json
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    import cv2
    import numpy as np

    OPENCV_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore
    np = None  # type: ignore
    OPENCV_AVAILABLE = False



def command_path(*names: str) -> str:
    """Return the first installed command from ``names``."""
    for name in names:
        path = shutil.which(name)
        if path is not None:
            return path
    choices = " or ".join(names)
    raise RuntimeError(f"Required command is not installed: {choices}")


def parse_args() -> argparse.Namespace:
    default_url = os.getenv("MEDIAMTX_RTSP_URL")
    parser = argparse.ArgumentParser(
        description="Stream a Raspberry Pi CSI camera to MediaMTX."
    )
    parser.add_argument(
        "--url",
        default=default_url,
        required=default_url is None,
        help=(
            "MediaMTX publishing URL, for example "
            "rtsp://203.0.113.10:8554/parking. Can also be set with "
            "MEDIAMTX_RTSP_URL."
        ),
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--bitrate",
        type=int,
        default=2_000_000,
        help="H.264 bitrate in bits per second (default: 2000000).",
    )
    default_spots = str(Path(__file__).parent / "spots.json")
    parser.add_argument(
        "--detect",
        action="store_true",
        default=True,
        help="Run OpenCV parking spot boundary & car detection (default: True).",
    )
    parser.add_argument(
        "--no-detect",
        action="store_false",
        dest="detect",
        help="Disable OpenCV detection and only stream.",
    )
    parser.add_argument(
        "--spots",
        default=default_spots,
        help="Path to JSON file containing predefined parking spot boundary boxes.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.18,
        help="Car presence feature density threshold (default: 0.18).",
    )
    parser.add_argument(
        "--backend-url",
        default=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"),
        help="ParkPulse backend URL to report detections (empty string to disable).",
    )
    parser.add_argument(
        "--camera-id",
        default=os.getenv("CAMERA_ID", "raspi-camera"),
        help="Camera identifier when reporting detections to the backend.",
    )
    parser.add_argument(
        "--show-window",
        action="store_true",
        help="Display OpenCV window with drawn boundaries and detection states.",
    )
    args = parser.parse_args()

    parsed_url = urlparse(args.url)
    if parsed_url.scheme != "rtsp" or not parsed_url.netloc:
        parser.error("--url must be a complete rtsp:// URL")
    if not parsed_url.path.strip("/"):
        example_port = f":{parsed_url.port}" if parsed_url.port else ":8554"
        example_url = f"rtsp://{parsed_url.hostname}{example_port}/parking"
        parser.error(
            f"--url must include a stream path, for example: {example_url}"
        )
    for name in ("width", "height", "fps", "bitrate"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name} must be greater than zero")
    return args


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class PredefinedBoundaryBox:
    """Predefined parking spot boundary box for car presence detection."""

    def __init__(
        self,
        spot_id: str,
        points: list[list[int]] | None = None,
        bbox: list[int] | None = None,
        threshold: float | None = None,
        history_size: int = 7,
    ) -> None:
        self.spot_id = spot_id
        self.custom_threshold = threshold
        self.history: deque[bool] = deque(maxlen=history_size)
        self.car_detected: bool = False
        self.confidence: float = 0.90
        self.last_density: float = 0.0

        if points:
            self.points = np.array(points, dtype=np.int32)
            self.x, self.y, self.w, self.h = cv2.boundingRect(self.points)
        elif bbox:
            self.x, self.y, self.w, self.h = bbox
            self.points = np.array(
                [
                    [self.x, self.y],
                    [self.x + self.w, self.y],
                    [self.x + self.w, self.y + self.h],
                    [self.x, self.y + self.h],
                ],
                dtype=np.int32,
            )
        else:
            raise ValueError(f"Spot {spot_id} must have points or bbox defined.")

        self.mask = np.zeros((self.h, self.w), dtype=np.uint8)
        local_pts = self.points - np.array([self.x, self.y])
        cv2.fillPoly(self.mask, [local_pts], 255)
        self.area = max(cv2.countNonZero(self.mask), 1)

    def evaluate(self, processed_frame: np.ndarray, default_threshold: float = 0.18) -> bool:
        frame_h, frame_w = processed_frame.shape[:2]
        x1, y1 = max(0, self.x), max(0, self.y)
        x2, y2 = min(frame_w, self.x + self.w), min(frame_h, self.y + self.h)
        if x2 <= x1 or y2 <= y1:
            return False

        roi = processed_frame[y1:y2, x1:x2]
        mask_roi = self.mask[0 : (y2 - y1), 0 : (x2 - x1)]
        masked_pixels = cv2.bitwise_and(roi, roi, mask=mask_roi)
        non_zero = cv2.countNonZero(masked_pixels)

        self.last_density = non_zero / self.area
        threshold = (
            self.custom_threshold
            if self.custom_threshold is not None
            else default_threshold
        )

        self.history.append(self.last_density > threshold)
        occupied_votes = sum(self.history)
        self.car_detected = occupied_votes >= (len(self.history) / 2.0)

        margin = abs(self.last_density - threshold) / max(threshold, 0.01)
        self.confidence = float(min(0.99, max(0.60, 0.70 + 0.29 * min(1.0, margin))))
        return self.car_detected


def load_predefined_boxes(spots_file: str | Path) -> list[PredefinedBoundaryBox]:
    path = Path(spots_file)
    default_spots = [
        {"spot_id": "A-1", "bbox": [100, 320, 160, 220]},
        {"spot_id": "A-2", "bbox": [300, 320, 160, 220]},
        {"spot_id": "A-3", "bbox": [500, 320, 160, 220]},
        {"spot_id": "A-4", "bbox": [700, 320, 160, 220]},
    ]
    if not path.is_file():
        return [PredefinedBoundaryBox(spot_id=item["spot_id"], bbox=item["bbox"]) for item in default_spots]
    try:
        with open(path, "r", encoding="utf-8") as file:
            raw_data = json.load(file)
        boxes = []
        for item in raw_data:
            spot_id = item.get("spot_id") or item.get("id", f"A-{len(boxes) + 1}")
            boxes.append(
                PredefinedBoundaryBox(
                    spot_id=spot_id,
                    points=item.get("points"),
                    bbox=item.get("bbox"),
                    threshold=item.get("threshold"),
                )
            )
        return boxes if boxes else [PredefinedBoundaryBox(spot_id=i["spot_id"], bbox=i["bbox"]) for i in default_spots]
    except Exception:
        return [PredefinedBoundaryBox(spot_id=item["spot_id"], bbox=item["bbox"]) for item in default_spots]


def preprocess_frame(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 1)
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 16
    )
    thresh = cv2.medianBlur(thresh, 5)
    kernel = np.ones((3, 3), np.uint8)
    return cv2.dilate(thresh, kernel, iterations=1)


def draw_boundaries(frame: np.ndarray, boxes: list[PredefinedBoundaryBox]) -> None:
    overlay = frame.copy()
    for box in boxes:
        fill_color = (34, 45, 220) if box.car_detected else (60, 180, 50)
        border_color = (0, 0, 255) if box.car_detected else (0, 255, 0)

        cv2.fillPoly(overlay, [box.points], fill_color)
        cv2.polylines(frame, [box.points], isClosed=True, color=border_color, thickness=2)

        cx, cy = int(box.x + box.w / 2), int(box.y + box.h / 2)
        status = "CAR" if box.car_detected else "EMPTY"
        label = f"{box.spot_id}: {status} ({int(box.last_density * 100)}%)"

        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
        text_x = max(0, cx - text_size[0] // 2)
        text_y = cy + text_size[1] // 2
        cv2.putText(frame, label, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)


def draw_hud(frame: np.ndarray, total: int, cars: int, fps: float) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 45), (25, 25, 25), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    text = f"SPOTS: {total}  |  AVAILABLE: {total - cars}  |  CARS DETECTED: {cars}  |  FPS: {fps:.1f}"
    cv2.putText(frame, text, (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)


def send_detections_to_backend(backend_url: str | None, camera_id: str, detections: list[dict]) -> None:
    if not backend_url:
        return
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "detections": detections,
    }
    endpoint = f"{backend_url.rstrip('/')}/api/cameras/{camera_id}/detections"
    try:
        req = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=2.0) as resp:
            pass
    except Exception:
        pass


def run_opencv(args: argparse.Namespace, stop_event: threading.Event) -> None:
    if not OPENCV_AVAILABLE:
        print("[OpenCV] opencv-python or numpy not installed; skipping local detection.")
        return

    # Connect to the local UDP stream generated by FFmpeg on port 8555
    udp_url = "udp://127.0.0.1:8555?overrun_nonfatal=1&fifo_size=50000000"
    print(f"[OpenCV] Listening to local camera feed on {udp_url}...")

    boxes = load_predefined_boxes(getattr(args, "spots", "spots.json"))
    window_name = "RasPi Parking Lot - Boundary & Car Detection"

    # Allow FFmpeg a brief moment to start pushing UDP packets
    time.sleep(1.0)

    cap = cv2.VideoCapture(udp_url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        # Fallback to RTSP URL if local UDP isn't ready
        cap = cv2.VideoCapture(args.url)

    if getattr(args, "show_window", False):
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    fps = 0.0
    frame_count = 0
    start_time = time.time()
    last_report_time = 0.0

    try:
        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            frame_count += 1
            now = time.time()
            if now - start_time >= 1.0:
                fps = frame_count / (now - start_time)
                frame_count = 0
                start_time = now

            processed = preprocess_frame(frame)
            cars_detected = 0
            detections = []

            for box in boxes:
                car_present = box.evaluate(processed, default_threshold=getattr(args, "threshold", 0.18))
                if car_present:
                    cars_detected += 1
                detections.append({
                    "spot_id": box.spot_id,
                    "available": not car_present,
                    "confidence": round(box.confidence, 2),
                })

            # Send periodic detections to backend
            if now - last_report_time >= 2.0:
                send_detections_to_backend(
                    getattr(args, "backend_url", None),
                    getattr(args, "camera_id", "raspi-camera"),
                    detections,
                )
                last_report_time = now

            # Draw visual boundaries
            draw_boundaries(frame, boxes)
            draw_hud(frame, len(boxes), cars_detected, fps)

            if getattr(args, "show_window", False):
                cv2.imshow(window_name, frame)
                if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                    break
    finally:
        cap.release()
        if getattr(args, "show_window", False):
            cv2.destroyAllWindows()
        print("[OpenCV] Detection thread stopped.")


def stream(args: argparse.Namespace) -> None:
    camera_binary = command_path("rpicam-vid", "libcamera-vid")
    ffmpeg_binary = command_path("ffmpeg")

    camera_command = [
        camera_binary,
        "--timeout",
        "0",
        "--nopreview",
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--framerate",
        str(args.fps),
        "--codec",
        "h264",
        "--libav-format",
        "h264",
        "--profile",
        "baseline",
        "--bitrate",
        str(args.bitrate),
        "--intra",
        str(args.fps),
        "--inline",
        "--output",
        "-",
    ]
    ffmpeg_command = [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "h264",
        "-r",
        str(args.fps),
        "-i",
        "pipe:0",

        # Send to MediaMTX hosted on AWS
        "-c:v",
        "copy",
        "-f",
        "rtsp",
        "-rtsp_transport",
        "tcp",
        args.url,

        # Local stream for OpenCV on RasPi (port 8555)
        "-c:v", "copy",
        "-f", "mpegts",
        "udp://127.0.0.1:8555"
    ]

    camera: subprocess.Popen[bytes] | None = None
    ffmpeg: subprocess.Popen[bytes] | None = None
    try:
        print(
            f"Publishing {args.width}x{args.height} at {args.fps} fps "
            f"to {args.url}",
            flush=True,
        )
        camera = subprocess.Popen(camera_command, stdout=subprocess.PIPE)
        if camera.stdout is None:
            raise RuntimeError("Could not open the camera output pipe")

        ffmpeg = subprocess.Popen(ffmpeg_command, stdin=camera.stdout)
        camera.stdout.close()

        stop_event = threading.Event()
        opencv_thread: threading.Thread | None = None
        if getattr(args, "detect", True):
            opencv_thread = threading.Thread(
                target=run_opencv,
                args=(args, stop_event),
                daemon=True,
            )
            opencv_thread.start()

        while True:
            camera_status = camera.poll()
            if camera_status is not None:
                raise RuntimeError(
                    f"Camera process stopped with exit code {camera_status}"
                )

            ffmpeg_status = ffmpeg.poll()
            if ffmpeg_status is not None:
                raise RuntimeError(
                    f"FFmpeg stopped with exit code {ffmpeg_status}"
                )
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping stream...", flush=True)
    finally:
        if "stop_event" in locals() and stop_event is not None:
            stop_event.set()
        if "opencv_thread" in locals() and opencv_thread is not None and opencv_thread.is_alive():
            opencv_thread.join(timeout=2.0)
        stop_process(ffmpeg)
        stop_process(camera)


def main() -> int:
    try:
        stream(parse_args())
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
