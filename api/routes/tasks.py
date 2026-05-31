from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user
from ..middleware.errors import AppHTTPException, ErrorCode

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}


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
    if not task.title or not task.title.strip():
        raise AppHTTPException(ErrorCode.INVALID_INPUT, "Task title is required")
    if task.reward_amount <= 0:
        raise AppHTTPException(ErrorCode.INVALID_INPUT, "Reward amount must be positive")
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
        raise AppHTTPException(ErrorCode.NOT_FOUND, "Task not found")
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
        raise AppHTTPException(ErrorCode.NOT_FOUND, "Task not found")
    if task.creator_id != user["id"]:
        raise AppHTTPException(ErrorCode.FORBIDDEN, "Only the creator can update status")
    if update.status not in VALID_STATUSES:
        raise AppHTTPException(
            ErrorCode.VALIDATION_ERROR,
            f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise AppHTTPException(ErrorCode.NOT_FOUND, "Task not found")
    if task.creator_id != user["id"]:
        raise AppHTTPException(ErrorCode.FORBIDDEN, "Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise AppHTTPException(ErrorCode.TASK_ERROR, "Cannot cancel an active or completed task")
    task.status = "cancelled"
    db.commit()
    return {"id": task.id, "status": "cancelled"}
