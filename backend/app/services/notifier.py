import asyncio
import logging
import time
from typing import Dict, List, Set
from fastapi import WebSocket

logger = logging.getLogger("server_monits.notifier")


class WebSocketNotifier:
    """Manages active browser WebSocket connections and throttles broadcast updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.last_sensor_broadcast: Dict[str, float] = {}  # sensor_id -> timestamp
        self.throttle_interval = 1.0  # max 1 update per sensor per second

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.debug(f"Client connected to /ws/live. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.debug(f"Client disconnected from /ws/live. Total clients: {len(self.active_connections)}")

    async def broadcast_json(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        dead_connections = set()
        for conn in list(self.active_connections):
            try:
                await conn.send_json(message)
            except Exception:
                dead_connections.add(conn)

        for dead in dead_connections:
            self.active_connections.discard(dead)

    async def broadcast_telemetry(self, sensor_id: str, data: dict, force: bool = False):
        """Broadcast live telemetry with per-sensor throttling (1s)."""
        now = time.time()
        last = self.last_sensor_broadcast.get(sensor_id, 0.0)

        if not force and (now - last < self.throttle_interval):
            return  # Throttled

        self.last_sensor_broadcast[sensor_id] = now
        payload = {
            "type": "telemetry",
            "sensor_id": sensor_id,
            "timestamp": now,
            **data,
        }
        await self.broadcast_json(payload)

    async def broadcast_alert(self, alert_data: dict):
        """Broadcast an alert immediately (no throttling)."""
        payload = {
            "type": "alert",
            "timestamp": time.time(),
            **alert_data,
        }
        await self.broadcast_json(payload)


notifier = WebSocketNotifier()

