"""Local OpenCV webcam tester for interactive parking spot boundary writing and car detection.

Allows you to test boundary creation and car/object presence detection on your
local webcam without needing the Raspberry Pi. Boundaries drawn with your mouse
are automatically saved and retained in spots.json across program restarts.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import cv2
import numpy as np

from auto_detect_spots import (
    detect_spots_from_frame,
    draw_candidate_overlay,
    generate_column_bay,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("webcam_test")


class PredefinedBoundaryBox:
    """Represents a boundary box and evaluates object/car presence."""

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

    def evaluate(self, processed_frame: np.ndarray, default_threshold: float = 0.30) -> bool:
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

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "spot_id": self.spot_id,
            "points": self.points.tolist(),
            "bbox": [int(self.x), int(self.y), int(self.w), int(self.h)],
        }
        if self.custom_threshold is not None:
            data["threshold"] = self.custom_threshold
        return data


class BoundaryEditor:
    """Manages parking spots and handles interactive mouse boundary drawing with auto-retention."""

    def __init__(self, spots_file: str | Path, default_threshold: float = 0.30) -> None:
        self.spots_file = Path(spots_file).resolve()
        self.default_threshold = default_threshold
        self.boxes: list[PredefinedBoundaryBox] = []
        self.current_points: list[list[int]] = []
        self.mouse_pos: tuple[int, int] = (0, 0)
        self.calibrating: bool = True
        self.status_message: str = ""
        self.status_timestamp: float = 0.0

        # Auto-detect state
        self.auto_candidates: list[dict[str, Any]] | None = None
        self.auto_reviewing: bool = False

        # Two-click Bay Generator state
        self.bay_mode: bool = False
        self.bay_p1: tuple[int, int] | None = None

        self.load_spots()

    def set_status(self, message: str) -> None:
        self.status_message = message
        self.status_timestamp = time.time()
        logger.info(message)

    def load_spots(self) -> None:
        self.boxes.clear()
        if not self.spots_file.is_file() or self.spots_file.stat().st_size == 0:
            self.set_status(f"Ready. Press 'a' to auto-detect spots from camera.")
            return

        try:
            with open(self.spots_file, "r", encoding="utf-8") as file:
                raw_data = json.load(file)
            for item in raw_data:
                spot_id = item.get("spot_id") or item.get("id", f"A-{len(self.boxes) + 1}")
                self.boxes.append(
                    PredefinedBoundaryBox(
                        spot_id=spot_id,
                        points=item.get("points"),
                        bbox=item.get("bbox"),
                        threshold=item.get("threshold"),
                    )
                )
            self.set_status(f"Loaded {len(self.boxes)} boundaries from {self.spots_file.name}")
        except Exception as error:
            logger.error("Failed to load %s: %s", self.spots_file, error)

    def save_spots(self) -> None:
        try:
            self.spots_file.parent.mkdir(parents=True, exist_ok=True)
            data = [box.to_dict() for box in self.boxes]
            with open(self.spots_file, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            self.set_status(f"Retained {len(self.boxes)} boundaries in {self.spots_file.name}")
        except Exception as error:
            logger.error("Failed to save %s: %s", self.spots_file, error)

    def auto_detect_from_frame(self, frame: np.ndarray) -> int:
        """Analyze the camera frame and present auto-detected candidates for review."""
        candidates = detect_spots_from_frame(frame)
        if candidates:
            self.auto_candidates = candidates
            self.auto_reviewing = True
            self.set_status(
                f"Auto-detected {len(candidates)} spots! ENTER=Accept & Save | ESC=Discard"
            )
            return len(candidates)
        else:
            self.set_status("No spots detected. Try adjusting angle or lighting.")
            return 0

    def accept_auto_candidates(self) -> None:
        """Accept auto-detected candidates and save immediately."""
        if not self.auto_candidates:
            return
        self.boxes.clear()
        for item in self.auto_candidates:
            self.boxes.append(
                PredefinedBoundaryBox(
                    spot_id=item["spot_id"],
                    points=item["points"],
                    bbox=item.get("bbox"),
                )
            )
        self.save_spots()
        self.set_status(f"Accepted & saved {len(self.boxes)} auto-detected boundaries!")
        self.auto_candidates = None
        self.auto_reviewing = False

    def cancel_auto_detect(self) -> None:
        """Cancel auto-detect review without altering current boundaries."""
        self.auto_candidates = None
        self.auto_reviewing = False
        self.set_status("Auto-detect cancelled. Existing boundaries kept.")

    def toggle_bay_mode(self) -> None:
        """Toggle two-click bay generator mode."""
        self.bay_mode = not self.bay_mode
        self.bay_p1 = None
        if self.bay_mode:
            self.calibrating = True
            self.set_status("Bay Generator: Click Top-Left corner of column")
        else:
            self.set_status("Bay Generator cancelled.")

    def clear_all_spots(self) -> None:
        """Clear all spots for a clean re-initialization."""
        self.boxes.clear()
        self.current_points.clear()
        self.auto_candidates = None
        self.auto_reviewing = False
        self.save_spots()
        self.set_status("Cleared all boundaries.")

    def on_mouse(self, event: int, x: int, y: int, flags: int, param: Any) -> None:
        self.mouse_pos = (x, y)
        if not self.calibrating:
            return

        # Handle Two-Click Bay Generator Mode
        if self.bay_mode:
            if event == cv2.EVENT_LBUTTONDOWN:
                if self.bay_p1 is None:
                    self.bay_p1 = (x, y)
                    self.set_status("Bay Generator: Click Bottom-Right corner of column")
                else:
                    new_spots = generate_column_bay(
                        self.bay_p1,
                        (x, y),
                        spot_height=16,
                        start_index=len(self.boxes) + 1,
                    )
                    for item in new_spots:
                        self.boxes.append(
                            PredefinedBoundaryBox(
                                spot_id=item["spot_id"],
                                points=item["points"],
                                bbox=item.get("bbox"),
                            )
                        )
                    self.save_spots()
                    self.set_status(f"Generated {len(new_spots)} spots in bay!")
                    self.bay_mode = False
                    self.bay_p1 = None
            elif event == cv2.EVENT_RBUTTONDOWN:
                self.bay_mode = False
                self.bay_p1 = None
                self.set_status("Bay Generator cancelled.")
            return

        # Normal mode: Left-click to add a corner point
        if event == cv2.EVENT_LBUTTONDOWN:
            self.current_points.append([x, y])
            if len(self.current_points) == 4:
                new_id = f"A-{len(self.boxes) + 1}"
                self.boxes.append(
                    PredefinedBoundaryBox(
                        spot_id=new_id,
                        points=self.current_points,
                    )
                )
                self.current_points = []
                self.save_spots()

        # Right-click to remove nearest boundary
        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.boxes:
                distances = [
                    np.linalg.norm(np.mean(box.points, axis=0) - np.array([x, y]))
                    for box in self.boxes
                ]
                nearest_idx = int(np.argmin(distances))
                removed = self.boxes.pop(nearest_idx)
                self.save_spots()

    def undo(self) -> None:
        if self.current_points:
            self.current_points.pop()
            self.set_status("Undid last point.")
        elif self.boxes:
            removed = self.boxes.pop()
            self.save_spots()


def preprocess_frame(frame: np.ndarray) -> np.ndarray:
    """Preprocess frame using adaptive thresholding and morphological filters."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 1)
    thresh = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        25,
        16,
    )
    thresh = cv2.medianBlur(thresh, 5)
    kernel = np.ones((3, 3), np.uint8)
    return cv2.dilate(thresh, kernel, iterations=1)


def draw_boundaries(
    frame: np.ndarray,
    editor: BoundaryEditor,
    show_details: bool = True,
) -> None:
    """Draw boundaries with translucent color overlay, crisp edges, and labels."""
    # When reviewing auto-detected candidates, render the candidate overlay
    if editor.auto_reviewing and editor.auto_candidates:
        candidate_frame = draw_candidate_overlay(frame, editor.auto_candidates)
        np.copyto(frame, candidate_frame)
        return

    overlay = frame.copy()

    for box in editor.boxes:
        fill_color = (34, 45, 220) if box.car_detected else (60, 180, 50)
        border_color = (0, 0, 255) if box.car_detected else (0, 255, 0)

        # Translucent fill + outline
        cv2.fillPoly(overlay, [box.points], fill_color)
        cv2.polylines(frame, [box.points], isClosed=True, color=border_color, thickness=2)

        cx, cy = int(box.x + box.w / 2), int(box.y + box.h / 2)
        status = "CAR DETECTED" if box.car_detected else "EMPTY"
        label = (
            f"{box.spot_id}: {status} ({int(box.last_density * 100)}%)"
            if show_details
            else f"{box.spot_id}: {status}"
        )

        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
        text_x = max(0, cx - text_size[0] // 2)
        text_y = cy + text_size[1] // 2
        cv2.putText(frame, label, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    # Blend translucent fill (35% opacity)
    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)

    # Bay Generator in-progress preview (rubberband rectangle)
    if editor.bay_mode and editor.bay_p1 is not None:
        p1 = editor.bay_p1
        p2 = editor.mouse_pos
        cv2.rectangle(frame, p1, p2, (0, 215, 255), 2)
        cv2.circle(frame, p1, 5, (0, 255, 255), -1)

    # In-progress single spot manual drawing preview
    if editor.calibrating and editor.current_points:
        pts = np.array(editor.current_points, dtype=np.int32)
        for pt in editor.current_points:
            cv2.circle(frame, tuple(pt), 5, (0, 255, 255), -1)
        if len(editor.current_points) > 1:
            cv2.polylines(frame, [pts], isClosed=False, color=(0, 255, 255), thickness=2)
        cv2.line(frame, tuple(editor.current_points[-1]), editor.mouse_pos, (0, 255, 255), 1, cv2.LINE_AA)


def draw_hud(
    frame: np.ndarray,
    editor: BoundaryEditor,
    cars: int,
    fps: float,
) -> None:
    """Render top HUD banner with stats, retention status, and keyboard controls."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 55), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    if editor.auto_reviewing:
        count = len(editor.auto_candidates) if editor.auto_candidates else 0
        stats_text = f"AUTO-DETECT RESULT: {count} SPOTS PROPOSED"
        cv2.putText(frame, stats_text, (15, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 255), 2, cv2.LINE_AA)
        mode_text = "[PRESS ENTER / 'y' TO CONFIRM & SAVE | ESC / 'n' TO DISCARD]"
        cv2.putText(frame, mode_text, (15, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
        return

    total = len(editor.boxes)
    stats_text = (
        f"TOTAL: {total}  |  "
        f"AVAILABLE: {total - cars}  |  "
        f"OCCUPIED: {cars}  |  "
        f"FPS: {fps:.1f}"
    )
    cv2.putText(frame, stats_text, (15, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

    now = time.time()
    if editor.status_message and (now - editor.status_timestamp < 3.0):
        mode_text = f"[{editor.status_message}]"
        color = (0, 255, 120)  # Bright green notification
    elif editor.bay_mode:
        if editor.bay_p1 is None:
            mode_text = "[BAY TOOL: Click TOP-LEFT corner of parking column/bay | 'b' cancel]"
        else:
            mode_text = "[BAY TOOL: Click BOTTOM-RIGHT corner to auto-generate bay | 'b' cancel]"
        color = (0, 215, 255)
    elif editor.calibrating:
        mode_text = "[SETUP: 'a' Auto-Detect | 'b' Bay Tool | 4 clicks=Spot | Right-click=Delete | 'd' Clear | 'c' Run]"
        color = (0, 220, 255)
    else:
        mode_text = "[LIVE DETECTION: 'c' Edit/Setup | 'a' Auto-Detect | 'r' Reload | 'p' Binary | 'q' Quit]"
        color = (200, 200, 200)

    cv2.putText(frame, mode_text, (15, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)


def send_to_backend(backend_url: str | None, camera_id: str, detections: list[dict[str, Any]]) -> None:
    """Optional sync to local FastAPI backend."""
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
        with urlopen(req, timeout=1.0) as resp:
            pass
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local OpenCV Webcam Boundary Writer & Car Detector"
    )
    parser.add_argument(
        "--source",
        default="0",
        help="Webcam device index (default: 0) or path to a video file.",
    )
    parser.add_argument(
        "--spots",
        default=str(Path(__file__).parent / "spots.json"),
        help="Path to save/load parking spot boundary boxes JSON.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="Car presence feature density / confidence threshold (default: 0.30 for 30%% minimum).",
    )
    parser.add_argument(
        "--backend-url",
        default=os.getenv("BACKEND_URL", ""),
        help="ParkPulse backend URL (e.g. http://127.0.0.1:8000). Leave empty to test offline.",
    )
    parser.add_argument(
        "--camera-id",
        default="local-webcam",
        help="Camera ID reported to the backend.",
    )
    parser.add_argument(
        "--auto-detect",
        action="store_true",
        help="Automatically detect parking spot boundaries on first camera frame.",
    )
    args = parser.parse_args()

    # Open webcam or video
    source_val: int | str = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(source_val)
    if not cap.isOpened():
        logger.error("Could not open webcam or video source: %s", args.source)
        sys.exit(1)

    editor = BoundaryEditor(args.spots, default_threshold=args.threshold)
    window_name = "ParkPulse - Local Webcam Boundary Writer"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, editor.on_mouse)

    logger.info("Webcam started! Press 'a' to auto-detect parking spots across the lot.")
    logger.info("Controls: 'a'=Auto-Detect | 'b'=Bay Tool | 'c'=Toggle Draw | 's'=Save | 'd'=Clear | 'q'=Quit")

    show_binary = False
    fps = 0.0
    frame_count = 0
    start_time = time.time()
    last_backend_report = 0.0
    auto_detected_on_start = False

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                # If reading video file, loop back to start
                if not args.source.isdigit():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                logger.warning("Empty frame from webcam. Retrying...")
                time.sleep(0.05)
                continue

            # Auto-detect on first frame if requested via CLI flag
            if args.auto_detect and not auto_detected_on_start:
                editor.auto_detect_from_frame(frame)
                editor.accept_auto_candidates()
                auto_detected_on_start = True

            frame_count += 1
            now = time.time()
            if now - start_time >= 1.0:
                fps = frame_count / (now - start_time)
                frame_count = 0
                start_time = now

            processed = preprocess_frame(frame)
            cars_detected = 0
            detections = []

            for box in editor.boxes:
                car_present = box.evaluate(processed, default_threshold=editor.default_threshold)
                if car_present:
                    cars_detected += 1
                detections.append({
                    "spot_id": box.spot_id,
                    "available": not car_present,
                    "confidence": round(box.confidence, 2),
                })

            # Send to backend if configured
            if args.backend_url and (now - last_backend_report >= 2.0):
                send_to_backend(args.backend_url, args.camera_id, detections)
                last_backend_report = now

            display_frame = (
                cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
                if show_binary
                else frame.copy()
            )

            draw_boundaries(display_frame, editor)
            draw_hud(
                display_frame,
                editor=editor,
                cars=cars_detected,
                fps=fps,
            )

            cv2.imshow(window_name, display_frame)

            # Check if user closed the window with the 'X' button
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                break

            key = cv2.waitKey(1) & 0xFF

            # Review mode keys
            if editor.auto_reviewing:
                if key in (13, ord("y"), ord("Y")):  # ENTER or 'y' to confirm
                    editor.accept_auto_candidates()
                elif key in (27, 8, ord("n"), ord("N")):  # ESC, Backspace, or 'n' to cancel
                    editor.cancel_auto_detect()
                continue

            if key in (ord("q"), 27):  # 'q' or Esc
                break
            elif key == ord("a"):
                editor.auto_detect_from_frame(frame)
            elif key == ord("b"):
                editor.toggle_bay_mode()
            elif key == ord("d"):
                editor.clear_all_spots()
            elif key == ord("c"):
                editor.calibrating = not editor.calibrating
                editor.set_status("Drawing mode: ACTIVE" if editor.calibrating else "Detection mode: ACTIVE")
            elif key == ord("s"):
                editor.save_spots()
            elif key == ord("r"):
                editor.load_spots()
            elif key == ord("u"):
                editor.undo()
            elif key == ord("p"):
                show_binary = not show_binary

    except KeyboardInterrupt:
        logger.info("Exiting...")
    finally:
        editor.save_spots()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

