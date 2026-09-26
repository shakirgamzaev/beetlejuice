"""Send deterministic fake camera detections to the backend for local demos."""

import argparse
import json
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def send_detections(backend_url: str, occupied_index: int) -> None:
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "detections": [
            {
                "spot_id": f"A-{index + 1}",
                "available": index != occupied_index,
                "confidence": 0.95,
            }
            for index in range(4)
        ],
    }
    request = Request(
        f"{backend_url.rstrip('/')}/api/cameras/demo-camera/detections",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        result = json.load(response)
    print(f"Occupied: A-{occupied_index + 1}; backend: {result}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--interval", type=float, default=3)
    args = parser.parse_args()

    print("Sending fake detections. Press Ctrl+C to stop.")
    occupied_index = 0
    try:
        while True:
            send_detections(args.url, occupied_index)
            occupied_index = (occupied_index + 1) % 4
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")


if __name__ == "__main__":
    main()
