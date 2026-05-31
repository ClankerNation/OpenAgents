from fastapi import WebSocket, WebSocketDisconnect
from typing import Set
import json, asyncio

class TaskWSManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()
    
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)
    
    def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)
    
    async def broadcast(self, task_id: str, status: str, data: dict = None):
        msg = json.dumps({"task_id": task_id, "status": status, "data": data})
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self.connections -= dead

ws_manager = TaskWSManager()

async def task_ws_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)