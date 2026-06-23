"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Set
from datetime import datetime
import json

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# In-memory WebSocket connection store (placeholder for production Redis/pub-sub)
active_connections: Set[WebSocket] = set()


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

    old_status = task.status
    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()

    # Broadcast real-time update to websocket subscribers
    await broadcast_task_update(task_id, old_status, update.status)

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
    db.commit()

    # Broadcast real-time update to websocket subscribers
    await broadcast_task_update(task_id, old_status, "cancelled")
    return {"id": task.id, "status": "cancelled"}


@router.websocket("/ws/task-updates")
async def task_updates_websocket(websocket: WebSocket):
    """Real-time websocket endpoint for task status updates.

    Clients connect here to receive live notifications when any task
    changes status. Each message is a JSON object with the task id,
    old status, and new status.
    """
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            # Keep connection alive; clients send "ping" to test liveness
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.utcnow().isoformat()}))
    except WebSocketDisconnect:
        active_connections.discard(websocket)


async def broadcast_task_update(task_id: int, old_status: str, new_status: str):
    """Send a status-change event to all connected websocket clients."""
    payload = json.dumps({
        "type": "task_status_update",
        "task_id": task_id,
        "old_status": old_status,
        "new_status": new_status,
        "timestamp": datetime.utcnow().isoformat(),
    })
    disconnected: Set[WebSocket] = set()
    for connection in active_connections:
        try:
            await connection.send_text(payload)
        except Exception:
            disconnected.add(connection)
    active_connections -= disconnected
