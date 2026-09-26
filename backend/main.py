import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "parking.db"
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]


class Detection(BaseModel):
    spot_id: str = Field(min_length=1)
    available: bool
    confidence: float = Field(ge=0, le=1)


class CameraUpdate(BaseModel):
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    detections: list[Detection] = Field(min_length=1)


class SpotState(BaseModel):
    spot_id: str
    available: bool
    confidence: float
    camera_id: str
    updated_at: datetime


class SpotEvent(SpotState):
    event_id: int


spots: dict[str, SpotState] = {}


def connect_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect_database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS spot_states (
                spot_id TEXT PRIMARY KEY,
                available INTEGER NOT NULL,
                confidence REAL NOT NULL,
                camera_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS spot_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id TEXT NOT NULL,
                available INTEGER NOT NULL,
                confidence REAL NOT NULL,
                camera_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_spot_events_spot_time
                ON spot_events (spot_id, updated_at DESC);
            """
        )


def state_from_row(row: sqlite3.Row) -> SpotState:
    return SpotState(
        spot_id=row["spot_id"],
        available=bool(row["available"]),
        confidence=row["confidence"],
        camera_id=row["camera_id"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def load_spots() -> dict[str, SpotState]:
    with connect_database() as connection:
        rows = connection.execute(
            "SELECT * FROM spot_states ORDER BY spot_id"
        ).fetchall()
    return {row["spot_id"]: state_from_row(row) for row in rows}


def save_spot_states(states: list[SpotState], changed_ids: set[str]) -> None:
    with connect_database() as connection:
        for state in states:
            values = (
                state.spot_id,
                int(state.available),
                state.confidence,
                state.camera_id,
                state.updated_at.isoformat(),
            )
            connection.execute(
                """
                INSERT INTO spot_states
                    (spot_id, available, confidence, camera_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(spot_id) DO UPDATE SET
                    available = excluded.available,
                    confidence = excluded.confidence,
                    camera_id = excluded.camera_id,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            if state.spot_id in changed_ids:
                connection.execute(
                    """
                    INSERT INTO spot_events
                        (spot_id, available, confidence, camera_id, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    values,
                )


def load_history(spot_id: str | None, limit: int) -> list[SpotEvent]:
    query = "SELECT * FROM spot_events"
    parameters: list[str | int] = []
    if spot_id is not None:
        query += " WHERE spot_id = ?"
        parameters.append(spot_id)
    query += " ORDER BY event_id DESC LIMIT ?"
    parameters.append(limit)

    with connect_database() as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [
        SpotEvent(
            event_id=row["event_id"],
            **state_from_row(row).model_dump(),
        )
        for row in rows
    ]


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    spots.clear()
    spots.update(load_spots())
    yield


app = FastAPI(title="Live Parking API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        disconnected: list[WebSocket] = []
        for websocket in list(self.connections):
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket)


manager = ConnectionManager()


def serialized_spots() -> list[dict]:
    return [
        spot.model_dump(mode="json")
        for spot in sorted(spots.values(), key=lambda item: item.spot_id)
    ]


@app.get("/")
async def root():
    return {
        "service": "Live Parking API",
        "status": "ok",
        "spots": "/api/spots",
        "camera_updates": "/api/cameras/{camera_id}/detections",
        "live_updates": "/ws/parking",
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/spots", response_model=list[SpotState])
async def get_spots():
    """Return the latest known state of every parking spot."""
    return sorted(spots.values(), key=lambda item: item.spot_id)


@app.get("/api/history", response_model=list[SpotEvent])
async def get_history(
    spot_id: str | None = None,
    limit: int = 50,
):
    """Return persisted availability transitions for analysis and prediction."""
    safe_limit = max(1, min(limit, 500))
    return load_history(spot_id, safe_limit)


@app.post("/api/cameras/{camera_id}/detections")
async def receive_detections(camera_id: str, update: CameraUpdate):
    """Receive the OpenCV result for one camera frame or sampling interval."""
    changed: list[SpotState] = []
    received: list[SpotState] = []
    captured_at = update.captured_at
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)

    for detection in update.detections:
        previous = spots.get(detection.spot_id)
        current = SpotState(
            spot_id=detection.spot_id,
            available=detection.available,
            confidence=detection.confidence,
            camera_id=camera_id,
            updated_at=captured_at,
        )
        spots[detection.spot_id] = current
        received.append(current)

        if previous is None or previous.available != current.available:
            changed.append(current)

    save_spot_states(received, {spot.spot_id for spot in changed})

    if changed:
        await manager.broadcast(
            {
                "type": "parking.updated",
                "camera_id": camera_id,
                "spots": [spot.model_dump(mode="json") for spot in changed],
            }
        )

    return {
        "accepted": len(update.detections),
        "changed": len(changed),
    }


@app.websocket("/ws/parking")
async def parking_updates(websocket: WebSocket):
    await manager.connect(websocket)
    await websocket.send_json(
        {
            "type": "parking.snapshot",
            "spots": serialized_spots(),
        }
    )

    try:
        while True:
            # Waiting for a message also lets FastAPI notice client disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
