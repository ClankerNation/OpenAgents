"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, task_id: int, websocket: WebSocket):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)

    def disconnect(self, task_id: int, websocket: WebSocket):
        if task_id in self.active_connections:
            self.active_connections[task_id] = [ws for ws in self.active_connections[task_id] if ws != websocket]
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

    async def broadcast_task_update(self, task_id: int, data: dict):
        if task_id in self.active_connections:
            stale = []
            for ws in self.active_connections[task_id]:
                try:
                    await ws.send_json(data)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                self.disconnect(task_id, ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket):
    await websocket.accept()
    subscriptions = set()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "subscribe" and msg.get("task_id"):
                subscriptions.add(msg["task_id"])
            elif msg.get("type") == "unsubscribe" and msg.get("task_id"):
                subscriptions.discard(msg["task_id"])
    except WebSocketDisconnect:
        for tid in subscriptions:
            manager.disconnect(tid, websocket)

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

    old_status = task.status
    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    await manager.broadcast_task_update(task.id, {"type": "status_change", "task_id": task.id, "old_status": old_status, "new_status": task.status})
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
    await manager.broadcast_task_update(task.id, {"type": "status_change", "task_id": task.id, "old_status": "cancelling", "new_status": "cancelled"})
    return {"id": task.id, "status": "cancelled"}
