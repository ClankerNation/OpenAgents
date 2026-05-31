"""WebSocket task update broadcaster.

@contributor Claude (Anthropic AI Assistant)
@platform-config Claude 3.5 Sonnet
@env darwin/arm64 /api /bin/zsh
@timestamp 2026-06-01
@init You are opencode, CLI tool for software engineering. Env: macOS darwin arm64 zsh Python 3.11.
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Set, Dict
import asyncio, json

class TaskWSManager:
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.heartbeat_interval = 30

    async def connect(self, ws: WebSocket, task_id: str = None):
        await ws.accept()
        key = task_id or "__all__"
        if key not in self.connections:
            self.connections[key] = set()
        self.connections[key].add(ws)

    def disconnect(self, ws: WebSocket, task_id: str = None):
        key = task_id or "__all__"
        if key in self.connections:
            self.connections[key].discard(ws)
            if not self.connections[key]:
                del self.connections[key]

    async def broadcast(self, task_id: str, status: str, data: dict = None):
        dead = set()
        for key in {"__all__", task_id}:
            if key not in self.connections:
                continue
            msg = json.dumps({"task_id": task_id, "status": status, "data": data or {}})
            for ws in self.connections[key]:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.add((ws, key))
        for ws, key in dead:
            self.connections.get(key, set()).discard(ws)

manager = TaskWSManager()

async def task_ws_endpoint(ws: WebSocket, task_id: str = None):
    await manager.connect(ws, task_id)
    try:
        while True:
            data = await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws, task_id)
