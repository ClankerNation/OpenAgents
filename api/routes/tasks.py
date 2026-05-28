"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user
from ..errors import NotFoundError, ForbiddenError, ValidationError

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
        raise ValidationError(
            message="Task title is required",
            fields=[{"field": "title", "message": "Title must not be empty", "type": "value_error"}],
        )
    if task.reward_amount <= 0:
        raise ValidationError(
            message="Reward amount must be positive",
            fields=[{"field": "reward_amount", "message": "Amount must be greater than zero", "type": "value_error"}],
        )
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
    limit: int = Query(50, ge=1, le=100),
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
        raise NotFoundError("Task", task_id)
    return task


@router.patch("/{task_id}/status")
async def update_task_status(
    task_id: int,
    update: TaskStatusUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    if update.status not in VALID_STATUSES:
        raise ValidationError(
            message=f"Invalid status: {update.status}",
            fields=[{
                "field": "status",
                "message": f"Must be one of: {', '.join(sorted(VALID_STATUSES))}",
                "type": "value_error",
            }],
        )
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise NotFoundError("Task", task_id)
    if task.creator_id != user["id"]:
        raise ForbiddenError("Only the creator can update task status")
    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise NotFoundError("Task", task_id)
    if task.creator_id != user["id"]:
        raise ForbiddenError("Only the creator can cancel a task")
    if task.status not in ("open", "assigned"):
        raise ValidationError(
            message="Cannot cancel an active task",
            fields=[{"field": "status", "message": "Task must be open or assigned to cancel", "type": "value_error"}],
        )
    task.status = "cancelled"
    db.commit()
    return {"id": task.id, "status": "cancelled"}
