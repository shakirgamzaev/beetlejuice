# Raspberry Pi Camera Streamer & Parking Spot Detector

This folder contains the camera streaming and computer vision occupancy detection code for the ParkPulse system.

---

## 1. Local Webcam Testing (`local_webcam_test.py`)

Test and calibrate parking spot boundaries directly on your laptop or desktop using your built-in or USB webcam without needing the Raspberry Pi.

### Run:
```bash
python local_webcam_test.py
```

Options:
* `--source 0` — Webcam index (default: `0`) or path to a recorded video file.
* `--spots spots.json` — Path to load and save boundary boxes (default: `spots.json`).
* `--threshold 0.18` — Feature density detection threshold (default: `0.18`).
* `--backend-url http://127.0.0.1:8000` — Sync live detections to local FastAPI backend.

### In-Window Mouse & Keyboard Controls:

| Key / Action | What it does |
|---|---|
| **Left-Click (4 times)** | Click the 4 corners of any parking space (or region on your desk) to create a boundary box. |
| **Right-Click** | Delete the boundary box nearest to the cursor. |
| **`u`** | Undo the last clicked point or delete the last created boundary. |
| **`s`** | **Save**: writes all drawn boundary boxes directly to `spots.json`. |
| **`c`** | **Toggle Drawing Mode**: turn on/off boundary drawing guide lines. |
| **`p`** | **Preview**: toggle between normal color camera feed and binary threshold filter. |
| **`q`** or **`Esc`** | Exit. |

---

## 2. Raspberry Pi Camera Streamer (`main.py`)

Runs on the Raspberry Pi:
1. Captures live video from the Pi camera via `rpicam-vid`.
2. Encodes and pushes an H.264 RTSP stream to the MediaMTX server via `ffmpeg`.
3. Simultaneously mirrors a local UDP stream (`udp://127.0.0.1:8555`) to run OpenCV parking spot detection in the background.
4. Reports occupancy updates to the ParkPulse FastAPI backend.

### Run on Raspberry Pi:
```bash
python main.py --url rtsp://<mediamtx-server-ip>:8554/parking
```

With local GUI window (if a monitor is connected to the Pi):
```bash
python main.py --url rtsp://<mediamtx-server-ip>:8554/parking --show-window
```

Stream only (skip OpenCV):
```bash
python main.py --url rtsp://<mediamtx-server-ip>:8554/parking --no-detect
```

