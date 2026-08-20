"""
@fix-author rafaio1
@date 2026-08-20T12:25:00Z
@runtime os=linux, arch=x64, working_dir=/tmp/OpenAgents, shell=bash
@platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

"""Task management endpoints for bounty assignments."""

import asyncio
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Set
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user


# --- WebSocket Manager for Real-Time Task Updates ---
class TaskWebSocketManager:
    """Manages WebSocket connections for real-time task updates."""
    
    def __init__(self):
        self.task_subscribers: Dict[int, Set[WebSocket]] = {}
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        for task_id in list(self.task_subscribers.keys()):
            self.task_subscribers[task_id].discard(websocket)
            if not self.task_subscribers[task_id]:
                del self.task_subscribers[task_id]
    
    def subscribe(self, websocket: WebSocket, task_id: int):
        if task_id not in self.task_subscribers:
            self.task_subscribers[task_id] = set()
        self.task_subscribers[task_id].add(websocket)
    
    def unsubscribe(self, websocket: WebSocket, task_id: int):
        if task_id in self.task_subscribers:
            self.task_subscribers[task_id].discard(websocket)
            if not self.task_subscribers[task_id]:
                del self.task_subscribers[task_id]
    
    async def broadcast_task_update(self, task_id: int, data: dict):
        message = json.dumps({"type": "task_update", "task_id": task_id, "data": data})
        subscribers = self.task_subscribers.get(task_id, set()).copy()
        for ws in subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(ws)
    
    async def send_heartbeat(self, websocket: WebSocket):
        try:
            while websocket in self.active_connections:
                await websocket.send_text(json.dumps({"type": "heartbeat", "timestamp": int(time.time())}))
                await asyncio.sleep(30)
        except Exception:
            self.disconnect(websocket)


ws_manager = TaskWebSocketManager()

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


@router.post("/")
async def create_task(task: TaskCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_task = Task(
        title=task.title,
        description=task.description,
        reward_amount=task.reward_amount,
        creator_id=user["id"],
        agent_id=task.agent_id,
        status="open",
        created_at=datetime.utcnow(),
        deadline=task.deadline,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return {"id": new_task.id, "status": new_task.status}


@router.get("/")
async def list_tasks(
    status: Optional[str] = None,
    creator: Optional[str] = None,
    skip: int = Query(0, ge=0),
    # BUG: No upper bound on limit — clients can request millions of rows,
    # causing DB strain and potential OOM
    limit: int = Query(50, ge=1),
    db=Depends(get_db),
):
    query = db.query(Task)
    if status:
        query = query.filter(Task.status == status)
    if creator:
        query = query.filter(Task.creator_id == creator)
    return query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{task_id}")
async def get_task(task_id: int, db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}/status")
async def update_task_status(
    task_id: int,
    update: TaskStatusUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # BUG: Creator can mark their own task as completed — should require
    # a third party or the assignee to confirm completion
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")
    task.status = "cancelled"
    db.commit()
    return {"id": task.id, "status": "cancelled"}


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates.
    
    Protocol:
    - Client sends: {"action": "subscribe", "task_id": 123}
    - Client sends: {"action": "unsubscribe", "task_id": 123}
    - Server sends: {"type": "task_update", "task_id": 123, "data": {...}}
    - Server sends: {"type": "heartbeat", "timestamp": 1234567890}
    """
    await ws_manager.connect(websocket)
    heartbeat_task = asyncio.create_task(ws_manager.send_heartbeat(websocket))
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")
                task_id = message.get("task_id")
                
                if action == "subscribe" and task_id is not None:
                    ws_manager.subscribe(websocket, int(task_id))
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "task_id": task_id
                    }))
                elif action == "unsubscribe" and task_id is not None:
                    ws_manager.unsubscribe(websocket, int(task_id))
                    await websocket.send_text(json.dumps({
                        "type": "unsubscribed",
                        "task_id": task_id
                    }))
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Invalid action. Use 'subscribe' or 'unsubscribe' with 'task_id'"
                    }))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON"
                }))
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        ws_manager.disconnect(websocket)
