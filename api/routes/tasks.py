"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Valid status transitions
VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}
MAX_PAGINATION_LIMIT = 100

# Allowed status transitions (from -> to)
VALID_TRANSITIONS = {
    "open": {"assigned", "cancelled"},
    "assigned": {"in_progress", "cancelled"},
    "in_progress": {"review", "cancelled"},
    "review": {"completed", "in_progress"},
    "completed": set(),
    "cancelled": set(),
}


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    reward_amount: float = Field(..., gt=0)
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None

    @validator('deadline')
    def validate_deadline(cls, v):
        if v is not None and v <= datetime.utcnow():
            raise ValueError('Deadline must be in the future')
        return v


class TaskStatusUpdate(BaseModel):
    status: str

    @validator('status')
    def validate_status(cls, v):
        if v not in VALID_STATUSES:
            raise ValueError(f'Invalid status. Must be one of: {", ".join(VALID_STATUSES)}')
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
    return {"id": new_task.id, "status": new_task.status}


@router.get("/")
async def list_tasks(
    status: Optional[str] = None,
    creator: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGINATION_LIMIT),
    db=Depends(get_db),
):
    query = db.query(Task)
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status filter. Must be one of: {', '.join(VALID_STATUSES)}")
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

    # Check deadline enforcement — auto-expire if past deadline
    if task.deadline and datetime.utcnow() > task.deadline and task.status not in ("completed", "cancelled"):
        task.status = "cancelled"
        task.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=400, detail="Task has expired and been cancelled")

    # Validate status transition
    current_transitions = VALID_TRANSITIONS.get(task.status, set())
    if update.status not in current_transitions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from '{task.status}' to '{update.status}'"
        )

    # Self-completion check: creator cannot mark their own task as completed
    if update.status == "completed" and task.creator_id == user["id"]:
        raise HTTPException(
            status_code=403,
            detail="Creator cannot mark their own task as completed"
        )

    # Assignment check: only assigned agent can start/review
    if update.status in ("in_progress", "review") and task.agent_id != user["id"]:
        raise HTTPException(
            status_code=403,
            detail="Only the assigned agent can update to this status"
        )

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
