"""WebSocket connection manager for real-time task updates.

Manages client connections, subscription to specific task IDs,
heartbeat, and cleanup of disconnected clients.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections with task ID subscription support."""

    def __init__(self):
        # Active connections: client_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}
        # Subscription map: task_id -> set of client_ids
        self.subscriptions: Dict[int, Set[int]] = {}
        # Reverse map: client_id -> set of task_ids
        self.client_subscriptions: Dict[int, Set[int]] = {}
        self._next_id: int = 1

    async def connect(self, websocket: WebSocket) -> int:
        """Accept a new WebSocket connection and return the client ID."""
        await websocket.accept()
        client_id = self._next_id
        self._next_id += 1
        self.active_connections[client_id] = websocket
        self.client_subscriptions[client_id] = set()
        logger.info(f"Client {client_id} connected. Active: {len(self.active_connections)}")
        return client_id

    def disconnect(self, client_id: int):
        """Remove a client and all its subscriptions."""
        self.active_connections.pop(client_id, None)
        subscribed_tasks = self.client_subscriptions.pop(client_id, set())
        for task_id in subscribed_tasks:
            if task_id in self.subscriptions:
                self.subscriptions[task_id].discard(client_id)
                if not self.subscriptions[task_id]:
                    del self.subscriptions[task_id]
        logger.info(f"Client {client_id} disconnected. Active: {len(self.active_connections)}")

    def subscribe(self, client_id: int, task_id: int):
        """Subscribe a client to updates for a specific task ID."""
        if task_id not in self.subscriptions:
            self.subscriptions[task_id] = set()
        self.subscriptions[task_id].add(client_id)
        self.client_subscriptions[client_id].add(task_id)
        logger.info(f"Client {client_id} subscribed to task {task_id}")

    def unsubscribe(self, client_id: int, task_id: int):
        """Unsubscribe a client from a specific task ID."""
        if task_id in self.subscriptions:
            self.subscriptions[task_id].discard(client_id)
            if not self.subscriptions[task_id]:
                del self.subscriptions[task_id]
        self.client_subscriptions[client_id].discard(task_id)
        logger.info(f"Client {client_id} unsubscribed from task {task_id}")

    def unsubscribe_all(self, client_id: int):
        """Unsubscribe a client from all task IDs."""
        subscribed = list(self.client_subscriptions.get(client_id, set()))
        for task_id in subscribed:
            self.unsubscribe(client_id, task_id)

    async def broadcast_task_update(self, task_id: int, event: str, data: dict):
        """Broadcast a task update to all clients subscribed to this task ID.

        Also broadcasts to unsubscribed clients if they want all task updates.
        """
        message = {
            "type": "task_update",
            "event": event,
            "task_id": task_id,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        subscribed_clients = self.subscriptions.get(task_id, set())
        # Send to subscribed clients
        for client_id in list(subscribed_clients):
            await self._safe_send(client_id, message)

        # Also send to all connected clients that haven't subscribed to anything
        # (they get all updates as a default)
        for client_id in list(self.active_connections.keys()):
            if client_id not in subscribed_clients and client_id in self.active_connections:
                subscriptions = self.client_subscriptions.get(client_id, set())
                if not subscriptions:
                    # No specific subscriptions — client gets all updates
                    await self._safe_send(client_id, message)

    async def send_personal_message(self, client_id: int, message: dict):
        """Send a message to a specific client."""
        await self._safe_send(client_id, message)

    async def _safe_send(self, client_id: int, message: dict):
        """Safely send a JSON message to a client, handling disconnections."""
        websocket = self.active_connections.get(client_id)
        if not websocket:
            return
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to client {client_id}: {e}")
            self.disconnect(client_id)

    async def send_heartbeat(self, client_id: int):
        """Send a heartbeat ping to a client."""
        await self._safe_send(client_id, {
            "type": "heartbeat",
            "timestamp": datetime.utcnow().isoformat(),
        })


# Global singleton
manager = ConnectionManager()


async def heartbeat_loop(client_id: int, interval: int = 30):
    """Send heartbeat pings to a client at regular intervals."""
    while client_id in manager.active_connections:
        await asyncio.sleep(interval)
        if client_id in manager.active_connections:
            await manager.send_heartbeat(client_id)
