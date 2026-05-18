"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json
import asyncio

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.task_subscriptions: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: Optional[int] = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        if task_id is not None:
            if task_id not in self.task_subscriptions:
                self.task_subscriptions[task_id] = []
            self.task_subscriptions[task_id].append(websocket)

    def disconnect(self, websocket: WebSocket, task_id: Optional[int] = None):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if task_id is not None and task_id in self.task_subscriptions:
            if websocket in self.task_subscriptions[task_id]:
                self.task_subscriptions[task_id].remove(websocket)

    async def broadcast(self, message: dict, task_id: Optional[int] = None):
        if task_id is not None and task_id in self.task_subscriptions:
            for connection in self.task_subscriptions[task_id][:]:
                try:
                    if connection.client_state == WebSocketState.CONNECTED:
                        await connection.send_json(message)
                except Exception:
                    pass
        else:
            for connection in self.active_connections[:]:
                try:
                    if connection.client_state == WebSocketState.CONNECTED:
                        await connection.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


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

    # Broadcast update to WebSocket subscribers
    await manager.broadcast({
        "type": "task_updated",
        "task_id": task.id,
        "status": task.status,
        "updated_at": task.updated_at.isoformat(),
    }, task_id)

    return {"id": task.id, "status": task.status}


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket, task_id: Optional[int] = None):
    """
    WebSocket endpoint for real-time task updates.
    Connect to /tasks/ws for all task updates,
    or /tasks/ws?task_id=N for updates on a specific task only.
    """
    await manager.connect(websocket, task_id)
    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)


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
