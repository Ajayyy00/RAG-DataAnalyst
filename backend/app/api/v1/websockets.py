import json
from typing import List

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import verify_token

log = structlog.get_logger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(
            "WebSocket client connected",
            active_connections=len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        log.info(
            "WebSocket client disconnected",
            active_connections=len(self.active_connections),
        )

    async def broadcast_event(self, message: dict):
        if not self.active_connections:
            return

        payload = json.dumps(message)
        dead_connections = []

        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception as e:
                log.warning(
                    "Failed to send WS message, removing connection", error=str(e)
                )
                dead_connections.append(connection)

        for dc in dead_connections:
            try:
                self.active_connections.remove(dc)
            except ValueError:
                pass


manager = ConnectionManager()


@router.websocket("/analytics")
async def websocket_endpoint(websocket: WebSocket):
    # ── Authentication (HttpOnly cookie preferred, query param fallback) ──────
    # This stream carries clinical events; reject unauthenticated clients
    # BEFORE accepting the socket.
    from app.config import get_settings

    settings = get_settings()
    token = websocket.cookies.get(settings.cookie_access_name) or (
        websocket.query_params.get("token")
    )
    payload = verify_token(token) if token else None
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001)
        return

    await manager.connect(websocket)
    try:
        while True:
            # We don't really expect incoming messages from frontend, just keep connection alive
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
