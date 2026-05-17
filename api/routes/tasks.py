"""
Task management endpoints for bounty assignments.

@contributor: Metatron (Hermes Agent v0.13.0, DeepSeek V4 Pro)
@platform-config: Autonomous coding agent operating on WSL/Linux x86_64
    Home: /home/power | Workdir: /home/power/OpenAgents | Shell: bash
@env: linux, x86_64, /home/power, /home/power/OpenAgents, bash
@timestamp: 2026-05-16T19:41:00Z

Defined endpoints:
  - GET /tasks/ — list tasks
  - POST /tasks/ — create task
  - GET /tasks/{task_id} — get single task
  - PATCH /tasks/{task_id}/status — update task status
  - DELETE /tasks/{task_id} — cancel task
  - WS /tasks/ws — WebSocket for real-time task updates
"""

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}


class TaskSubscriptionManager:
    """Manages WebSocket connections and task-id-based subscriptions."""

    def __init__(self):
        self._connections: dict[int, set[WebSocket]] = {}   # task_id -> {websockets}
        self._all_connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._all_connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._all_connections.discard(ws)
        for task_id in list(self._connections.keys()):
            self._connections[task_id].discard(ws)
            if not self._connections[task_id]:
                del self._connections[task_id]

    def subscribe(self, task_id: int, ws: WebSocket) -> None:
        if task_id not in self._connections:
            self._connections[task_id] = set()
        self._connections[task_id].add(ws)

    def unsubscribe(self, task_id: int, ws: WebSocket) -> None:
        if task_id in self._connections:
            self._connections[task_id].discard(ws)
            if not self._connections[task_id]:
                del self._connections[task_id]

    async def broadcast(self, task_id: int, event: str, data: dict) -> None:
        """Broadcast an event to all clients subscribed to a task."""
        if task_id not in self._connections:
            return
        payload = json.dumps({"task_id": task_id, "event": event, "data": data})
        dead = []
        for ws in self._connections.get(task_id, set()):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = TaskSubscriptionManager()


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
    await manager.broadcast(
        task_id,
        "status_change",
        {"id": task.id, "status": task.status, "updated_at": task.updated_at.isoformat()},
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
    db.commit()
    await manager.broadcast(
        task_id,
        "status_change",
        {"id": task.id, "status": task.status, "updated_at": datetime.utcnow().isoformat()},
    )
    return {"id": task.id, "status": "cancelled"}


@router.websocket("/ws")
async def task_websocket(ws: WebSocket):
    """
    WebSocket endpoint for real-time task updates.

    Client messages (JSON):
      {"action": "subscribe", "task_id": <int>}   — subscribe to task updates
      {"action": "unsubscribe", "task_id": <int>} — unsubscribe from task updates

    Server messages (JSON):
      {"task_id": <int>, "event": "status_change", "data": {...}}
      {"event": "heartbeat"}

    Heartbeat is sent every 30 seconds. Disconnected clients are cleaned up automatically.
    """
    await manager.connect(ws)
    try:
        heartbeat_task = asyncio.create_task(_heartbeat_loop(ws))
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps({"error": "invalid JSON"}))
                    continue

                action = msg.get("action")
                task_id = msg.get("task_id")

                if action == "subscribe" and isinstance(task_id, int):
                    manager.subscribe(task_id, ws)
                    await ws.send_text(json.dumps({"subscribed": task_id}))
                elif action == "unsubscribe" and isinstance(task_id, int):
                    manager.unsubscribe(task_id, ws)
                    await ws.send_text(json.dumps({"unsubscribed": task_id}))
                else:
                    await ws.send_text(
                        json.dumps({
                            "error": "unknown action",
                            "valid_actions": ["subscribe", "unsubscribe"],
                        })
                    )
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


async def _heartbeat_loop(ws: WebSocket) -> None:
    """Send heartbeat pings every 30 seconds to keep the connection alive."""
    while True:
        await asyncio.sleep(30)
        try:
            await ws.send_text(json.dumps({"event": "heartbeat"}))
        except Exception:
            break
