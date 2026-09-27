"""Publish the Raspberry Pi camera to MediaMTX as an H.264 RTSP stream."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse


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
        # Reduce frame buffering in the Pi's libav/libx264 software encoder.
        "--low-latency",
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
        "info",
        "-stats",
        "-f",
        "h264",
        "-r",
        str(args.fps),
        "-i",
        "pipe:0",
        "-c:v",
        "copy",
        "-f",
        "rtsp",
        "-rtsp_transport",
        "tcp",
        args.url,
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
