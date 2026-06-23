"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import Optional, Dict, List
from datetime import datetime
import json

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# In-memory WebSocket client registry (replace with Redis in production)
_task_subscribers: Dict[int, List[WebSocket]] = {}


# Contributor traceability header
# @contributor Gaotax2006
# @platform claude-code/opus-4.8
# @runtime node-v24.15.0 / win32 / amd64
# @date 2026-06-24
# @fixes #188 — Added WebSocket endpoint ws/tasks/ws for real-time task updates


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
    def status_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}")
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
        created_at=datetime.utcnow(),
        deadline=task.deadline,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    _broadcast_task_update(new_task.id, {"event": "created", "task": {"id": new_task.id, "status": new_task.status}})
    return {"id": new_task.id, "status": new_task.status}


@router.get("/")
async def list_tasks(
    status: Optional[str] = None,
    creator: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
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
    if old_status != task.status:
        _broadcast_task_update(task_id, {
            "event": "status_change",
            "task_id": task_id,
            "old_status": old_status,
            "new_status": task.status,
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
    task.status = "cancelled"
    db.commit()
    _broadcast_task_update(task_id, {
        "event": "cancelled",
        "task_id": task_id,
    })
    return {"id": task.id, "status": "cancelled"}


# ---- WebSocket support (fix #188) ----

def _broadcast_task_update(task_id: int, payload: dict):
    """Send a JSON payload to all subscribers of a given task."""
    if task_id in _task_subscribers:
        dead: List[WebSocket] = []
        data = json.dumps(payload)
        for ws in _task_subscribers[task_id]:
            try:
                import asyncio
                asyncio.get_event_loop().create_task(ws.send_text(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            _task_subscribers[task_id].remove(ws)


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates.

    Clients connect to /tasks/ws and subscribe to task IDs via JSON messages:
      {"action": "subscribe", "task_id": 42}
      {"action": "unsubscribe", "task_id": 42}
    """
    await websocket.accept()
    subscribed_tasks: set = set()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            action = msg.get("action", "")
            task_id = msg.get("task_id")

            if action == "subscribe" and task_id is not None:
                tid = int(task_id)
                subscribed_tasks.add(tid)
                _task_subscribers.setdefault(tid, []).append(websocket)
                await websocket.send_json({"event": "subscribed", "task_id": tid})

            elif action == "unsubscribe" and task_id is not None:
                tid = int(task_id)
                subscribed_tasks.discard(tid)
                if tid in _task_subscribers:
                    try:
                        _task_subscribers[tid].remove(websocket)
                    except ValueError:
                        pass

            else:
                await websocket.send_json({"error": "Unknown action. Use subscribe/unsubscribe."})

    except WebSocketDisconnect:
        for tid in list(subscribed_tasks):
            if tid in _task_subscribers:
                try:
                    _task_subscribers[tid].remove(websocket)
                except ValueError:
                    pass
    except Exception:
        pass
