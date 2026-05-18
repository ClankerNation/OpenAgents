"""
@contributor: hermes-agent
@platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
@env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
@timestamp: 2026-05-18
"""

"""Task management endpoints for bounty assignments."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Set, Dict, List
from collections import defaultdict

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user
from ..middleware.errors import NotFoundError, ForbiddenError, BadRequestError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# ---------------------------------------------------------------------------
# TaskBroadcaster — manages WebSocket connections and subscriptions
# ---------------------------------------------------------------------------

class TaskBroadcaster:
    """Manages WebSocket connections for real-time task updates.

    Clients connect, then send subscribe/unsubscribe messages to filter
    which task IDs they care about. State-change broadcasts are sent only
    to clients subscribed to the relevant task (or all clients with no
    subscriptions). Heartbeat pings are sent every 30 seconds.
    """

    PING_INTERVAL: float = 30.0  # seconds between heartbeat pings

    def __init__(self) -> None:
        # websocket -> set of subscribed task_ids (empty = receive all)
        self._subscriptions: Dict[WebSocket, Set[int]] = {}
        # reverse index: task_id -> set of websockets subscribed to it
        self._task_subscribers: Dict[int, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    # -- connection lifecycle ------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        """Accept a WebSocket and start tracking it."""
        await ws.accept()
        async with self._lock:
            self._subscriptions[ws] = set()
        logger.info("WS client connected: %s", ws.client)

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket from all tracking structures."""
        async with self._lock:
            subscribed_tasks = self._subscriptions.pop(ws, set())
            for task_id in subscribed_tasks:
                self._task_subscribers[task_id].discard(ws)
                if not self._task_subscribers[task_id]:
                    del self._task_subscribers[task_id]
        try:
            await ws.close()
        except Exception:
            pass
        logger.info("WS client disconnected: %s", ws.client)

    # -- subscription management ---------------------------------------------

    async def subscribe(self, ws: WebSocket, task_id: int) -> None:
        """Subscribe a connected client to updates for *task_id*."""
        async with self._lock:
            if ws in self._subscriptions:
                self._subscriptions[ws].add(task_id)
                self._task_subscribers[task_id].add(ws)

    async def unsubscribe(self, ws: WebSocket, task_id: int) -> None:
        """Remove *task_id* from a client's subscription set."""
        async with self._lock:
            if ws in self._subscriptions:
                self._subscriptions[ws].discard(task_id)
            self._task_subscribers[task_id].discard(ws)
            if not self._task_subscribers.get(task_id):
                self._task_subscribers.pop(task_id, None)

    # -- broadcasting --------------------------------------------------------

    async def broadcast_state_change(self, task_id: int, data: dict) -> None:
        """Send *data* to every client subscribed to *task_id* and to
        clients that have no subscriptions (receive-all mode)."""
        message = json.dumps({"type": "task_update", "task_id": task_id, **data})
        async with self._lock:
            recipients: Set[WebSocket] = set()
            # Clients subscribed to this specific task
            recipients.update(self._task_subscribers.get(task_id, set()))
            # Clients with no subscriptions (receive-all)
            for ws, subs in self._subscriptions.items():
                if not subs:
                    recipients.add(ws)
        for ws in list(recipients):
            try:
                await ws.send_text(message)
            except Exception:
                logger.warning("Failed to send to %s, removing", ws.client)
                await self.disconnect(ws)

    # -- heartbeat -----------------------------------------------------------

    async def heartbeat_loop(self, ws: WebSocket) -> None:
        """Send periodic ping frames until the connection closes."""
        try:
            while True:
                await asyncio.sleep(self.PING_INTERVAL)
                await ws.send_text(json.dumps({"type": "ping"}))
        except Exception:
            # Connection likely closed — cleanup happens in the caller
            pass

    # -- introspection helpers (for testing) ---------------------------------

    @property
    def connection_count(self) -> int:
        return len(self._subscriptions)

    def is_subscribed(self, ws: WebSocket, task_id: int) -> bool:
        subs = self._subscriptions.get(ws)
        return subs is not None and task_id in subs

    def get_subscriptions(self, ws: WebSocket) -> Set[int]:
        return self._subscriptions.get(ws, set()).copy()


# Module-level singleton used by the WebSocket endpoint
broadcaster = TaskBroadcaster()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


class WSMessage(BaseModel):
    """Incoming WebSocket message schema."""
    action: str  # "subscribe" | "unsubscribe"
    task_id: Optional[int] = None

# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

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
    # Broadcast the new task to WebSocket clients
    await broadcaster.broadcast_state_change(new_task.id, {
        "status": new_task.status,
        "title": new_task.title,
        "action": "created",
    })
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
        raise NotFoundError("Task not found")
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
        raise NotFoundError("Task not found")

    # BUG: Creator can mark their own task as completed — should require
    # a third party or the assignee to confirm completion
    if task.creator_id != user["id"]:
        raise ForbiddenError("Only the creator can update status")

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    # Broadcast the state change to WebSocket clients
    await broadcaster.broadcast_state_change(task.id, {
        "status": task.status,
        "title": task.title,
        "action": "status_update",
    })
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise NotFoundError("Task not found")
    if task.creator_id != user["id"]:
        raise ForbiddenError("Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise BadRequestError("Cannot cancel an active task")
    task.status = "cancelled"
    db.commit()
    # Broadcast cancellation
    await broadcaster.broadcast_state_change(task.id, {
        "status": "cancelled",
        "title": task.title,
        "action": "cancelled",
    })
    return {"id": task.id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def task_ws(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates.

    Clients can send JSON messages:
      {"action": "subscribe",   "task_id": <int>}  — receive updates for task
      {"action": "unsubscribe", "task_id": <int>}  — stop receiving updates for task

    Server sends:
      {"type": "task_update", "task_id": <int>, ...}  — task state change
      {"type": "pong"}                                 — heartbeat response to ping
      {"type": "ping"}                                  — server heartbeat ping
    """
    await broadcaster.connect(websocket)
    heartbeat_task = asyncio.create_task(broadcaster.heartbeat_loop(websocket))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "detail": "Invalid JSON"}))
                continue

            action = msg.get("action")
            task_id = msg.get("task_id")

            if action == "subscribe":
                if task_id is None:
                    await websocket.send_text(json.dumps({"type": "error", "detail": "task_id required"}))
                    continue
                await broadcaster.subscribe(websocket, int(task_id))
                await websocket.send_text(json.dumps({"type": "subscribed", "task_id": int(task_id)}))
            elif action == "unsubscribe":
                if task_id is None:
                    await websocket.send_text(json.dumps({"type": "error", "detail": "task_id required"}))
                    continue
                await broadcaster.unsubscribe(websocket, int(task_id))
                await websocket.send_text(json.dumps({"type": "unsubscribed", "task_id": int(task_id)}))
            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            else:
                await websocket.send_text(json.dumps({"type": "error", "detail": f"Unknown action: {action}"}))

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Unexpected WS error")
    finally:
        heartbeat_task.cancel()
        await broadcaster.disconnect(websocket)