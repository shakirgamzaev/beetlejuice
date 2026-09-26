# ParkPulse backend MVP

ParkPulse receives parking-space detections, persists state changes, and pushes
live availability to a SvelteKit client.

## Run the demo

Start the API:

```bash
uv run uvicorn main:app --reload
```

Start the fake camera in another terminal:

```bash
uv run python simulate_camera.py
```

## Camera contract

The OpenCV process sends detection results to:

```text
POST /api/cameras/{camera_id}/detections
```

```json
{
  "captured_at": "2026-09-26T12:00:00Z",
  "detections": [
    {"spot_id": "A-1", "available": true, "confidence": 0.96},
    {"spot_id": "A-2", "available": false, "confidence": 0.91}
  ]
}
```

Only availability transitions are added to history. The latest confidence and
observation time are updated for every accepted detection.

Useful endpoints:

- `GET /api/spots` — current state
- `GET /api/history` — recent transitions
- `GET /api/history?spot_id=A-1` — transitions for one space
- `WS /ws/parking` — live snapshot and update messages

## SvelteKit connection

During development, HTTP requests from `http://localhost:5173` and
`http://127.0.0.1:5173` are allowed. Override the comma-separated list with the
`FRONTEND_ORIGINS` environment variable when deploying.

Fetch the initial state with `GET http://127.0.0.1:8000/api/spots`, then connect
to `ws://127.0.0.1:8000/ws/parking`. The first WebSocket message is a complete
snapshot:

```json
{"type": "parking.snapshot", "spots": []}
```

Later messages contain only spaces whose availability changed:

```json
{
  "type": "parking.updated",
  "camera_id": "camera-1",
  "spots": [
    {
      "spot_id": "A-1",
      "available": true,
      "confidence": 0.96,
      "camera_id": "camera-1",
      "updated_at": "2026-09-26T12:00:00Z"
    }
  ]
}
```
