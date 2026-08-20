# @contributor rafaio1
# @timestamp 2026-08-20T12:55:00Z
# @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Task management endpoints for bounty assignments with WebSocket real-time updates."""

import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        # task_id -> set of websockets subscribed to that task
        self.task_subscribers: dict[int, set[WebSocket]] = {}
        # websocket -> set of task_ids subscribed
        self.ws_subscriptions: dict[WebSocket, set[int]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.ws_subscriptions[websocket] = set()

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            tasks = self.ws_subscriptions.pop(websocket, set())
            for task_id in tasks:
                subs = self.task_subscribers.get(task_id)
                if subs:
                    subs.discard(websocket)
                    if not subs:
                        del self.task_subscribers[task_id]

    async def subscribe(self, websocket: WebSocket, task_id: int):
        async with self._lock:
            if task_id not in self.task_subscribers:
                self.task_subscribers[task_id] = set()
            self.task_subscribers[task_id].add(websocket)
            self.ws_subscriptions[websocket].add(task_id)

    async def unsubscribe(self, websocket: WebSocket, task_id: int):
        async with self._lock:
            subs = self.task_subscribers.get(task_id)
            if subs:
                subs.discard(websocket)
                if not subs:
                    del self.task_subscribers[task_id]
            ws_tasks = self.ws_subscriptions.get(websocket)
            if ws_tasks:
                ws_tasks.discard(task_id)

    async def broadcast_task_update(self, task_id: int, data: dict):
        async with self._lock:
            subscribers = list(self.task_subscribers.get(task_id, set()))
        message = json.dumps({"type": "task_update", "task_id": task_id, **data})
        disconnected = []
        for ws in subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            await self.disconnect(ws)

manager = ConnectionManager()


@router.websocket("/ws")
async def tasks_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Heartbeat ping every 30 seconds handled by client timeout
            # Listen for subscription messages
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            try:
                msg = json.loads(data)
                action = msg.get("action")
                task_id = msg.get("task_id")
                if action == "subscribe" and task_id is not None:
                    await manager.subscribe(websocket, int(task_id))
                    await websocket.send_text(json.dumps({"type": "subscribed", "task_id": task_id}))
                elif action == "unsubscribe" and task_id is not None:
                    await manager.unsubscribe(websocket, int(task_id))
                    await websocket.send_text(json.dumps({"type": "unsubscribed", "task_id": task_id}))
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        await manager.disconnect(websocket)


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str


@router.post("/")
async def create_task(task: TaskCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_task = Task(
        title=task.title,
        description=task.description,
        reward_amount=task.reward_amount,
        creator_id=user["id"],
        agent_id=task.agent_id,
        status="open",
        created_at=datetime.now(timezone.utc),
        deadline=task.deadline,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    result = {"id": new_task.id, "status": new_task.status}
    await manager.broadcast_task_update(new_task.id, result)
    return result


@router.get("/")
async def list_tasks(
    status: Optional[str] = None,
    creator: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
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
    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    old_status = task.status
    task.status = update.status
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    result = {"id": task.id, "status": task.status, "old_status": old_status}
    await manager.broadcast_task_update(task_id, result)
    return result


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
    result = {"id": task.id, "status": "cancelled"}
    await manager.broadcast_task_update(task_id, result)
    return result
