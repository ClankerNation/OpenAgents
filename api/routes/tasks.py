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


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


HEARTBEAT_INTERVAL_SECONDS = 30


def _serialize_task_update(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "agent_id": task.agent_id,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _extract_task_ids(message: dict) -> set[int]:
    raw_ids = message.get("task_ids")
    if raw_ids is None and "task_id" in message:
        raw_ids = [message.get("task_id")]
    if raw_ids is None:
        return set()
    if not isinstance(raw_ids, list):
        raw_ids = [raw_ids]

    parsed: set[int] = set()
    for value in raw_ids:
        try:
            task_id = int(value)
        except (TypeError, ValueError):
            continue
        if task_id > 0:
            parsed.add(task_id)
    return parsed


class TaskWebSocketManager:
    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()
        self.subscriptions: dict[int, set[WebSocket]] = {}
        self.connection_subscriptions: dict[WebSocket, set[int]] = {}
        self.heartbeat_tasks: dict[WebSocket, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        self.connection_subscriptions[websocket] = set()
        self.heartbeat_tasks[websocket] = asyncio.create_task(self._heartbeat_loop(websocket))

    async def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

        subscribed_task_ids = self.connection_subscriptions.pop(websocket, set())
        for task_id in subscribed_task_ids:
            listeners = self.subscriptions.get(task_id)
            if not listeners:
                continue
            listeners.discard(websocket)
            if not listeners:
                self.subscriptions.pop(task_id, None)

        heartbeat_task = self.heartbeat_tasks.pop(websocket, None)
        if heartbeat_task and heartbeat_task is not asyncio.current_task():
            heartbeat_task.cancel()

    async def subscribe(self, websocket: WebSocket, task_ids: set[int]) -> list[int]:
        subscribed_task_ids = self.connection_subscriptions.setdefault(websocket, set())
        for task_id in task_ids:
            listeners = self.subscriptions.setdefault(task_id, set())
            listeners.add(websocket)
            subscribed_task_ids.add(task_id)
        return sorted(subscribed_task_ids)

    async def unsubscribe(self, websocket: WebSocket, task_ids: set[int]) -> list[int]:
        subscribed_task_ids = self.connection_subscriptions.setdefault(websocket, set())
        for task_id in task_ids:
            listeners = self.subscriptions.get(task_id)
            if listeners:
                listeners.discard(websocket)
                if not listeners:
                    self.subscriptions.pop(task_id, None)
            subscribed_task_ids.discard(task_id)
        return sorted(subscribed_task_ids)

    async def broadcast_task_update(self, task: Task) -> None:
        listeners = list(self.subscriptions.get(task.id, set()))
        if not listeners:
            return

        payload = {"type": "task_update", "task": _serialize_task_update(task)}
        for websocket in listeners:
            try:
                await websocket.send_json(payload)
            except Exception:
                await self.disconnect(websocket)

    async def _heartbeat_loop(self, websocket: WebSocket) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
        except Exception:
            await self.disconnect(websocket)


task_ws_manager = TaskWebSocketManager()


@router.websocket("/ws")
async def task_updates_websocket(websocket: WebSocket):
    await task_ws_manager.connect(websocket)
    await websocket.send_json({"type": "connected"})
    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            task_ids = _extract_task_ids(message)

            if action == "subscribe":
                subscribed = await task_ws_manager.subscribe(websocket, task_ids)
                await websocket.send_json({"type": "subscribed", "task_ids": subscribed})
            elif action == "unsubscribe":
                subscribed = await task_ws_manager.unsubscribe(websocket, task_ids)
                await websocket.send_json({"type": "unsubscribed", "task_ids": subscribed})
            else:
                await websocket.send_json({"type": "error", "detail": "Unsupported action"})
    except WebSocketDisconnect:
        await task_ws_manager.disconnect(websocket)


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
    await task_ws_manager.broadcast_task_update(new_task)
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
    db.refresh(task)
    await task_ws_manager.broadcast_task_update(task)
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
    db.refresh(task)
    await task_ws_manager.broadcast_task_update(task)
    return {"id": task.id, "status": "cancelled"}
