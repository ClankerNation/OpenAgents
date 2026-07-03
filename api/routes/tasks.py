"""Task management endpoints for bounty assignments with WebSocket support."""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import asyncio
import json

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user
from .websocket_manager import manager, heartbeat_loop

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

    # Broadcast task creation
    await manager.broadcast_task_update(
        new_task.id,
        "created",
        {"title": new_task.title, "status": new_task.status, "reward_amount": new_task.reward_amount},
    )

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

    old_status = task.status
    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()

    # Broadcast status change
    await manager.broadcast_task_update(
        task_id,
        "status_changed",
        {"old_status": old_status, "new_status": update.status},
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

    # Broadcast cancellation
    await manager.broadcast_task_update(
        task_id,
        "cancelled",
        {"status": "cancelled"},
    )

    return {"id": task.id, "status": "cancelled"}


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates.

    Protocol:
    - Connect: opens the WebSocket
    - Subscribe: {"type": "subscribe", "task_id": <int>}
    - Unsubscribe: {"type": "unsubscribe", "task_id": <int>}
    - UnsubscribeAll: {"type": "unsubscribe_all"}
    - Server sends: {"type": "task_update", "event": "...", "task_id": ..., "data": {...}, "timestamp": "..."}
    - Server sends: {"type": "heartbeat", "timestamp": "..."} every 30 seconds
    """
    client_id = await manager.connect(websocket)

    # Start heartbeat loop
    heartbeat_task = asyncio.create_task(heartbeat_loop(client_id))

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type")

            if msg_type == "subscribe":
                task_id = data.get("task_id")
                if task_id is None or not isinstance(task_id, int):
                    await websocket.send_json({"type": "error", "message": "task_id must be an integer"})
                    continue
                manager.subscribe(client_id, task_id)
                await websocket.send_json({
                    "type": "subscribed",
                    "task_id": task_id,
                })

            elif msg_type == "unsubscribe":
                task_id = data.get("task_id")
                if task_id is None or not isinstance(task_id, int):
                    await websocket.send_json({"type": "error", "message": "task_id must be an integer"})
                    continue
                manager.unsubscribe(client_id, task_id)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "task_id": task_id,
                })

            elif msg_type == "unsubscribe_all":
                manager.unsubscribe_all(client_id)
                await websocket.send_json({"type": "unsubscribed_all"})

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}. Valid types: subscribe, unsubscribe, unsubscribe_all",
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        heartbeat_task.cancel()
        manager.disconnect(client_id)
