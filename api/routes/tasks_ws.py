# @contributor rafaio1
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for WebSocket task updates (Issue #188)
# @env linux x64 /root /tmp/openagents_issue_188 bash
# @timestamp 2026-08-25T07:00:00Z
"""WebSocket endpoint for real-time task status updates with subscription filtering and heartbeat.

Closes #188
"""
import asyncio
import json
import time
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["tasks"])

# Connection manager: tracks active WebSocket connections and their subscriptions
_connections: Dict[WebSocket, Set[int]] = {}
_lock = asyncio.Lock()

HEARTBEAT_INTERVAL = 30  # seconds


async def broadcast_task_update(task_id: int, status: str, updated_at: str):
    """Broadcast a task state change to all subscribed clients."""
    message = json.dumps({
        "type": "task_update",
        "task_id": task_id,
        "status": status,
        "updated_at": updated_at,
    })
    disconnected = []
    async with _lock:
        for ws, subscriptions in _connections.items():
            if task_id in subscriptions or not subscriptions:  # empty set = subscribe to all
                try:
                    await ws.send_text(message)
                except Exception:
                    disconnected.append(ws)
    # Clean up broken connections outside the lock iteration
    for ws in disconnected:
        async with _lock:
            _connections.pop(ws, None)


@router.websocket("/tasks/ws")
async def tasks_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates.

    Protocol:
    - Client sends JSON {"action": "subscribe", "task_ids": [1, 2, 3]} to filter
    - Client sends JSON {"action": "unsubscribe", "task_ids": [1]} to remove filters
    - Client sends JSON {"action": "ping"} for manual heartbeat
    - Server sends {"type": "pong"} every 30s to keep connection alive
    - Server sends {"type": "task_update", ...} on subscribed task changes
    - Empty subscription set means receive ALL task updates
    """
    await websocket.accept()
    subscriptions: Set[int] = set()

    async with _lock:
        _connections[websocket] = subscriptions

    last_heartbeat = time.time()

    try:
        while True:
            # Check heartbeat timeout
            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": int(now)}))
                last_heartbeat = now

            # Wait for client message with timeout to allow heartbeat checks
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            action = msg.get("action")
            if action == "subscribe":
                task_ids = msg.get("task_ids", [])
                if isinstance(task_ids, list):
                    subscriptions.update(int(tid) for tid in task_ids if isinstance(tid, (int, str)))
                await websocket.send_text(json.dumps({
                    "type": "subscribed",
                    "task_ids": list(subscriptions),
                }))
            elif action == "unsubscribe":
                task_ids = msg.get("task_ids", [])
                if isinstance(task_ids, list):
                    subscriptions.difference_update(int(tid) for tid in task_ids if isinstance(tid, (int, str)))
                await websocket.send_text(json.dumps({
                    "type": "unsubscribed",
                    "task_ids": list(subscriptions),
                }))
            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": int(time.time())}))
                last_heartbeat = time.time()
            else:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Unknown action: {action}",
                }))

    except WebSocketDisconnect:
        pass
    finally:
        async with _lock:
            _connections.pop(websocket, None)
