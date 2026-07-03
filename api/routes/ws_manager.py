"""
WebSocket connection manager for real-time task updates.

Manages active connections per user, supports broadcasting task status
changes to all connected clients or targeted subscribers.
"""

import logging
import json
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger("openagents.ws")


class ConnectionManager:
    """
    Manages active WebSocket connections, keyed by user ID.

    Each user can have multiple simultaneous connections (tabs/devices).
    """

    def __init__(self):
        # user_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        # reverse map: websocket -> user_id for O(1) disconnect cleanup
        self._reverse: Dict[int, str] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept a new WebSocket connection for a user."""
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        self._reverse[id(websocket)] = user_id
        logger.info(
            "WebSocket connected: user=%s, total_connections=%d",
            user_id,
            self.active_connections,
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        ws_id = id(websocket)
        user_id = self._reverse.pop(ws_id, None)
        if user_id and user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
            logger.info(
                "WebSocket disconnected: user=%s, total_connections=%d",
                user_id,
                self.active_connections,
            )

    async def broadcast(self, message: dict):
        """Send a message to ALL connected clients."""
        payload = json.dumps(message)
        stale = []
        for user_id, sockets in list(self._connections.items()):
            for ws in list(sockets):
                try:
                    await ws.send_text(payload)
                except Exception:
                    stale.append(ws)
            # Clean stale connections
            for ws in stale:
                self.disconnect(ws)
            stale.clear()

    async def broadcast_to_user(self, user_id: str, message: dict):
        """Send a message to all connections for a specific user."""
        sockets = self._connections.get(user_id)
        if not sockets:
            return
        payload = json.dumps(message)
        stale = []
        for ws in list(sockets):
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)

    @property
    def active_connections(self) -> int:
        """Total number of active WebSocket connections."""
        return sum(len(socks) for socks in self._connections.values())

    @property
    def connected_users(self) -> int:
        """Number of distinct connected users."""
        return len(self._connections)


# Singleton instance — shared across the application
manager = ConnectionManager()
