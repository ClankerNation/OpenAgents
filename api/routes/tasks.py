"""
@contributor: Metatron (Hermes Agent)
@platform-config: You are Metatron's autonomous bounty-hunting loop. You wake up every 30 minutes to generate income.
MANDATORY STARTUP: Check status of ALL open PRs by invisiblemonsters on ClankerNation/OpenAgents.
IF A PR NEEDS CHANGES: Read review comments, fix code, push fix.
IF ALL PRs ARE CLEAN: Read bounty_board.md, work on highest priority unclaimed bounty.
RULES: Never work on issue with existing open PR. Prefer Solidity. Add traceability header. Update CONTRIBUTORS.json.
@env: linux, x64, /home/power, /home/power/projects/OpenAgents, bash
@timestamp: 2026-05-17T00:20:00Z

Task management endpoints for bounty assignments with WebSocket real-time updates.
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


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


# ─── WebSocket Connection Manager ───────────────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections for real-time task updates."""

    def __init__(self):
        # task_id -> set of WebSocket connections subscribed to that task
        self._subscriptions: dict[int, set[WebSocket]] = {}
        # WebSocket -> set of task_ids the client is subscribed to
        self._client_tasks: dict[WebSocket, set[int]] = {}

    async def subscribe(self, websocket: WebSocket, task_id: int) -> None:
        """Subscribe a WebSocket client to updates for a specific task."""
        self._subscriptions.setdefault(task_id, set()).add(websocket)
        self._client_tasks.setdefault(websocket, set()).add(task_id)

    async def unsubscribe(self, websocket: WebSocket, task_id: int) -> None:
        """Unsubscribe a WebSocket client from a specific task."""
        if task_id in self._subscriptions:
            self._subscriptions[task_id].discard(websocket)
            if not self._subscriptions[task_id]:
                del self._subscriptions[task_id]
        if websocket in self._client_tasks:
            self._client_tasks[websocket].discard(task_id)
            if not self._client_tasks[websocket]:
                del self._client_tasks[websocket]

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket client from all subscriptions on disconnect."""
        if websocket in self._client_tasks:
            for task_id in list(self._client_tasks[websocket]):
                if task_id in self._subscriptions:
                    self._subscriptions[task_id].discard(websocket)
                    if not self._subscriptions[task_id]:
                        del self._subscriptions[task_id]
            del self._client_tasks[websocket]

    async def broadcast(self, task_id: int, message: dict) -> None:
        """Send a message to all clients subscribed to a task."""
        if task_id not in self._subscriptions:
            return
        dead: list[WebSocket] = []
        payload = json.dumps(message)
        for ws in list(self._subscriptions[task_id]):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """Send a message to a specific WebSocket client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            await self.disconnect(websocket)

    def get_subscription_count(self) -> int:
        """Return total number of active subscriptions."""
        return sum(len(s) for s in self._subscriptions.values())


manager = ConnectionManager()


# ─── WebSocket Endpoint ─────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_task_updates(websocket: WebSocket):
    """
    WebSocket endpoint for real-time task state updates.

    Client sends JSON messages:
      {"action": "subscribe", "task_id": <int>}
      {"action": "unsubscribe", "task_id": <int>}

    Server broadcasts:
      {"type": "task_update", "task_id": <int>, "status": <str>, "timestamp": <iso-str>}
      {"type": "task_created", "task_id": <int>, "title": <str>, "timestamp": <iso-str>}
      {"type": "task_cancelled", "task_id": <int>, "timestamp": <iso-str>}
      {"type": "heartbeat", "timestamp": <iso-str>}
      {"type": "subscribed", "task_id": <int>}
      {"type": "unsubscribed", "task_id": <int>}
      {"type": "error", "message": <str>}
    """
    await websocket.accept()

    async def heartbeat_loop():
        """Send periodic heartbeat pings every 30 seconds."""
        while True:
            try:
                await asyncio.sleep(30)
                await manager.send_personal(
                    websocket,
                    {"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()},
                )
            except Exception:
                break

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_personal(
                    websocket,
                    {"type": "error", "message": "Invalid JSON"},
                )
                continue

            action = data.get("action")
            task_id = data.get("task_id")

            if action == "subscribe":
                if not isinstance(task_id, int):
                    await manager.send_personal(
                        websocket,
                        {"type": "error", "message": "task_id must be an integer"},
                    )
                    continue
                await manager.subscribe(websocket, task_id)
                await manager.send_personal(
                    websocket,
                    {"type": "subscribed", "task_id": task_id},
                )

            elif action == "unsubscribe":
                if not isinstance(task_id, int):
                    await manager.send_personal(
                        websocket,
                        {"type": "error", "message": "task_id must be an integer"},
                    )
                    continue
                await manager.unsubscribe(websocket, task_id)
                await manager.send_personal(
                    websocket,
                    {"type": "unsubscribed", "task_id": task_id},
                )

            else:
                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "message": f"Unknown action: {action}. Use 'subscribe' or 'unsubscribe'.",
                    },
                )

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await manager.disconnect(websocket)


# ─── REST Endpoints (with broadcast hooks) ──────────────────────────────────


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

    # Broadcast task creation to subscribers
    await manager.broadcast(
        new_task.id,
        {
            "type": "task_created",
            "task_id": new_task.id,
            "title": new_task.title,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    return {"id": new_task.id, "status": new_task.status}


@router.get("/")
async def list_tasks(
    status: Optional[str] = None,
    creator: Optional[str] = None,
    skip: int = Query(0, ge=0),
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

    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    old_status = task.status
    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()

    # Broadcast status change to subscribers
    await manager.broadcast(
        task_id,
        {
            "type": "task_update",
            "task_id": task_id,
            "old_status": old_status,
            "new_status": update.status,
            "timestamp": datetime.utcnow().isoformat(),
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
    db.commit()

    # Broadcast cancellation to subscribers
    await manager.broadcast(
        task_id,
        {
            "type": "task_cancelled",
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    return {"id": task.id, "status": "cancelled"}


# ─── WebSocket Status Endpoint ──────────────────────────────────────────────

@router.get("/ws/status")
async def websocket_status():
    """Return the number of active WebSocket connections and subscriptions."""
    return {
        "active_subscriptions": manager.get_subscription_count(),
    }
