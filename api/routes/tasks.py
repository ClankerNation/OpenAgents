# @contributor-info rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Task management endpoints for bounty assignments."""

import asyncio
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, timezone

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        # task_id -> set of websockets
        self.subscriptions: dict[int, set[WebSocket]] = {}
        # websocket -> set of task_ids
        self.client_subs: dict[WebSocket, set[int]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.client_subs[ws] = set()

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            task_ids = self.client_subs.pop(ws, set())
            for tid in task_ids:
                self.subscriptions.get(tid, set()).discard(ws)
                if not self.subscriptions.get(tid):
                    self.subscriptions.pop(tid, None)

    async def subscribe(self, ws: WebSocket, task_id: int):
        async with self._lock:
            if task_id not in self.subscriptions:
                self.subscriptions[task_id] = set()
            self.subscriptions[task_id].add(ws)
            self.client_subs.setdefault(ws, set()).add(task_id)

    async def unsubscribe(self, ws: WebSocket, task_id: int):
        async with self._lock:
            self.subscriptions.get(task_id, set()).discard(ws)
            if not self.subscriptions.get(task_id):
                self.subscriptions.pop(task_id, None)
            self.client_subs.get(ws, set()).discard(task_id)

    async def broadcast(self, task_id: int, message: dict):
        async with self._lock:
            subscribers = list(self.subscriptions.get(task_id, set()))
        dead = []
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

manager = ConnectionManager()


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")
        return v


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
    return {"id": new_task.id, "status": new_task.status}


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
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    old_status = task.status
    task.status = update.status
    task.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Broadcast status change to WebSocket subscribers
    await manager.broadcast(task_id, {
        "type": "status_update",
        "task_id": task_id,
        "old_status": old_status,
        "new_status": update.status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

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
    
    old_status = task.status
    task.status = "cancelled"
    task.updated_at = datetime.now(timezone.utc)
    db.commit()

    await manager.broadcast(task_id, {
        "type": "status_update",
        "task_id": task_id,
        "old_status": old_status,
        "new_status": "cancelled",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"id": task.id, "status": "cancelled"}


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            action = msg.get("action")
            task_id = msg.get("task_id")

            if action == "subscribe" and task_id is not None:
                await manager.subscribe(websocket, int(task_id))
                await websocket.send_json({"type": "subscribed", "task_id": task_id})
            elif action == "unsubscribe" and task_id is not None:
                await manager.unsubscribe(websocket, int(task_id))
                await websocket.send_json({"type": "unsubscribed", "task_id": task_id})
            elif action == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
            else:
                await websocket.send_json({"error": f"Unknown action: {action}"})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
