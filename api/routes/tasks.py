"""Task management endpoints for bounty assignments."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}
HEARTBEAT_INTERVAL_SECONDS = 30


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


class TaskWebSocketManager:
    def __init__(self):
        self.clients: dict[WebSocket, set[int]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients[websocket] = set()

    def disconnect(self, websocket: WebSocket) -> None:
        self.clients.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, task_id: int) -> None:
        self.clients.setdefault(websocket, set()).add(task_id)

    def unsubscribe(self, websocket: WebSocket, task_id: int) -> None:
        self.clients.setdefault(websocket, set()).discard(task_id)

    async def broadcast(self, task_id: int, payload: dict) -> None:
        stale: list[WebSocket] = []
        for websocket, task_ids in list(self.clients.items()):
            if task_id not in task_ids:
                continue
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                stale.append(websocket)

        for websocket in stale:
            self.disconnect(websocket)


task_ws_manager = TaskWebSocketManager()


async def broadcast_task_update(task_id: int, status: str) -> None:
    await task_ws_manager.broadcast(
        task_id,
        {"type": "task_update", "task_id": task_id, "status": status},
    )


@router.websocket("/ws")
async def task_updates_ws(websocket: WebSocket):
    await task_ws_manager.connect(websocket)
    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=HEARTBEAT_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
                continue

            action = message.get("action")
            task_id = int(message.get("task_id", 0))

            if action == "subscribe":
                task_ws_manager.subscribe(websocket, task_id)
                await websocket.send_json({"type": "subscribed", "task_id": task_id})
            elif action == "unsubscribe":
                task_ws_manager.unsubscribe(websocket, task_id)
                await websocket.send_json({"type": "unsubscribed", "task_id": task_id})
            else:
                await websocket.send_json({"type": "error", "message": "Unknown action"})
    except WebSocketDisconnect:
        task_ws_manager.disconnect(websocket)


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
    await broadcast_task_update(new_task.id, new_task.status)
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
    await broadcast_task_update(task.id, task.status)
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
    await broadcast_task_update(task.id, task.status)
    return {"id": task.id, "status": "cancelled"}
