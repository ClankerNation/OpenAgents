"""Task management API with WebSocket support for real-time updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Dict, Set, Optional
from datetime import datetime

router = APIRouter(prefix="/tasks", tags=["tasks"])

class TaskResponse(BaseModel):
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str

class TaskConnectionManager:
    """Manages WebSocket connections per task for real-time updates."""
    
    def __init__(self):
        self.active: Dict[int, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, task_id: int):
        await websocket.accept()
        if task_id not in self.active:
            self.active[task_id] = set()
        self.active[task_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, task_id: int):
        if task_id in self.active:
            self.active[task_id].discard(websocket)
            if not self.active[task_id]:
                del self.active[task_id]
    
    async def broadcast(self, task_id: int, message: dict):
        if task_id in self.active:
            dead = []
            for ws in self.active[task_id]:
                try:
                    await ws.send_json(message)
                except:
                    dead.append(ws)
            for ws in dead:
                self.active[task_id].discard(ws)

task_manager = TaskConnectionManager()

@router.websocket("/{task_id}/ws")
async def task_updates(websocket: WebSocket, task_id: int):
    """WebSocket endpoint for real-time task status updates.
    
    Clients connect to /tasks/{task_id}/ws to receive:
    - Status changes (pending, in_progress, completed, cancelled)
    - New submissions
    - Reward updates
    - Deadline extensions
    """
    await task_manager.connect(websocket, task_id)
    try:
        while True:
            data = await websocket.receive_text()
            await task_manager.broadcast(task_id, {
                "task_id": task_id,
                "update": data,
                "timestamp": datetime.now().isoformat(),
            })
    except WebSocketDisconnect:
        task_manager.disconnect(websocket, task_id)
    except Exception:
        task_manager.disconnect(websocket, task_id)

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    """Get task details."""
    raise HTTPException(status_code=404, detail="Task not found")

@router.get("/")
async def list_tasks():
    """List all tasks."""
    return {"tasks": [], "total": 0}
