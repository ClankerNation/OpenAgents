"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, timezone

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# Valid status transitions: current_status -> set of allowed next statuses
VALID_TRANSITIONS = {
    "open": {"assigned", "cancelled"},
    "assigned": {"in_progress", "open", "cancelled"},
    "in_progress": {"review", "cancelled"},
    "review": {"completed", "in_progress"},
    "completed": set(),  # terminal state
    "cancelled": set(),  # terminal state
}

MAX_PAGE_LIMIT = 100


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_in_future(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return v
        now = datetime.now(timezone.utc)
        deadline = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if deadline <= now:
            raise ValueError("Deadline must be in the future")
        return v


class TaskStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
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
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
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

    # Prevent creator from completing their own task
    if update.status == "completed" and task.creator_id == user["id"]:
        raise HTTPException(
            status_code=403,
            detail="Task creator cannot mark their own task as completed",
        )

    # Validate status transition
    allowed = VALID_TRANSITIONS.get(task.status, set())
    if update.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{task.status}' to '{update.status}'. "
            f"Allowed transitions: {', '.join(sorted(allowed)) if allowed else 'none (terminal state)'}",
        )

    # Enforce deadline: reject status changes on expired tasks
    if task.deadline:
        deadline = task.deadline if task.deadline.tzinfo else task.deadline.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > deadline and update.status not in ("cancelled",):
            raise HTTPException(
                status_code=400,
                detail="Cannot update status of an expired task. Deadline has passed.",
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
