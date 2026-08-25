"""Task management endpoints for bounty assignments.
@contributor rafaio1
@timestamp 2026-08-25T01:40:00Z
@env linux x64 /tmp/openagents_issue_202 bash
@platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

import asyncio
import json
import time
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set

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

# --- WebSocket Manager for Real-Time Task Updates (Issue #188) ---
class TaskWebSocketManager:
    """Manages WebSocket connections and task-specific subscriptions."""

    def __init__(self):
        # task_id -> set of websocket connections
        self._subscriptions: Dict[int, Set[WebSocket]] = {}
        # websocket -> set of subscribed task_ids
        self._client_subs: Dict[WebSocket, Set[int]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._client_subs[ws] = set()

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            subs = self._client_subs.pop(ws, set())
            for task_id in subs:
                self._subscriptions.get(task_id, set()).discard(ws)
                if not self._subscriptions.get(task_id):
                    self._subscriptions.pop(task_id, None)

    async def subscribe(self, ws: WebSocket, task_id: int):
        async with self._lock:
            if task_id not in self._subscriptions:
                self._subscriptions[task_id] = set()
            self._subscriptions[task_id].add(ws)
            self._client_subs.setdefault(ws, set()).add(task_id)

    async def unsubscribe(self, ws: WebSocket, task_id: int):
        async with self._lock:
            self._subscriptions.get(task_id, set()).discard(ws)
            if not self._subscriptions.get(task_id):
                self._subscriptions.pop(task_id, None)
            self._client_subs.get(ws, set()).discard(task_id)

    async def broadcast_task_update(self, task_id: int, event: dict):
        async with self._lock:
            clients = list(self._subscriptions.get(task_id, set()))
        dead = []
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


_ws_manager = TaskWebSocketManager()


@router.websocket("/ws")
async def tasks_websocket(ws: WebSocket):
    """WebSocket endpoint for real-time task updates.

    Protocol:
      Client sends JSON: {"action": "subscribe", "task_id": 123}
      Client sends JSON: {"action": "unsubscribe", "task_id": 123}
      Server sends JSON: {"type": "task_update", "task_id": 123, "status": "...", ...}
      Server sends JSON: {"type": "heartbeat", "timestamp": 1234567890}
    """
    await _ws_manager.connect(ws)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                msg = json.loads(raw)
                action = msg.get("action")
                task_id = msg.get("task_id")
                if action == "subscribe" and task_id is not None:
                    await _ws_manager.subscribe(ws, int(task_id))
                    await ws.send_json({"type": "subscribed", "task_id": int(task_id)})
                elif action == "unsubscribe" and task_id is not None:
                    await _ws_manager.unsubscribe(ws, int(task_id))
                    await ws.send_json({"type": "unsubscribed", "task_id": int(task_id)})
                else:
                    await ws.send_json({"type": "error", "message": "Unknown action or missing task_id"})
            except asyncio.TimeoutError:
                # Heartbeat ping every 30 seconds
                await ws.send_json({"type": "heartbeat", "timestamp": int(time.time())})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await _ws_manager.disconnect(ws)


def get_ws_manager() -> TaskWebSocketManager:
    """Return the singleton WebSocket manager for use in route handlers."""
    return _ws_manager

