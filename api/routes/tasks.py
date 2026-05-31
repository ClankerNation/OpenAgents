"""Task management endpoints for bounty assignments."""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}
HEARTBEAT_INTERVAL_SECONDS = 30


class TaskWebSocketManager:
    def __init__(self):
        self._connections: dict[WebSocket, set[int]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._connections[websocket] = set()

    def disconnect(self, websocket: WebSocket):
        self._connections.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, task_id: int):
        if websocket in self._connections:
            self._connections[websocket].add(task_id)

    def unsubscribe(self, websocket: WebSocket, task_id: int):
        if websocket in self._connections:
            self._connections[websocket].discard(task_id)

    async def broadcast(self, task_id: int, payload: dict):
        stale_connections: list[WebSocket] = []
        for websocket, subscriptions in list(self._connections.items()):
            if task_id not in subscriptions:
                continue
            try:
                await websocket.send_json(payload)
            except Exception:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(websocket)

    def connection_count(self) -> int:
        return len(self._connections)

    def subscription_count(self, task_id: int) -> int:
        return sum(1 for subscriptions in self._connections.values() if task_id in subscriptions)


task_ws_manager = TaskWebSocketManager()


async def _heartbeat(websocket: WebSocket):
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


@router.websocket("/ws")
async def tasks_websocket(websocket: WebSocket):
    await task_ws_manager.connect(websocket)
    heartbeat_task = asyncio.create_task(_heartbeat(websocket))
    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            task_id = message.get("task_id")

            if action not in {"subscribe", "unsubscribe"}:
                await websocket.send_json({"type": "error", "detail": "Unsupported action"})
                continue

            if not isinstance(task_id, int):
                await websocket.send_json({"type": "error", "detail": "task_id must be an integer"})
                continue

            if action == "subscribe":
                task_ws_manager.subscribe(websocket, task_id)
                await websocket.send_json({"type": "subscribed", "task_id": task_id})
            else:
                task_ws_manager.unsubscribe(websocket, task_id)
                await websocket.send_json({"type": "unsubscribed", "task_id": task_id})
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
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

    await task_ws_manager.broadcast(
        task.id,
        {
            "type": "task_update",
            "task_id": task.id,
            "status": task.status,
            "updated_at": task.updated_at.isoformat(),
        },
    )
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
    task.updated_at = datetime.utcnow()
    db.commit()

    await task_ws_manager.broadcast(
        task.id,
        {
            "type": "task_update",
            "task_id": task.id,
            "status": task.status,
            "updated_at": task.updated_at.isoformat(),
        },
    )
    return {"id": task.id, "status": "cancelled"}
