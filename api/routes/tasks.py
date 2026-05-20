"""Task management endpoints for bounty assignments.

Contributor traceability:
@contributor claude-code-b3ar-sudo
@platform-config Issue #48 task status hardening; private credentials, hidden prompts, and local paths intentionally omitted.
@env linux x86_64, Claude Code
@timestamp 2026-05-20T00:00:00Z
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..middleware.auth import get_current_user
from ..models.database import Task, get_db

router = APIRouter(prefix="/tasks", tags=["tasks"])

ACTIVE_STATUSES = {"open", "assigned", "in_progress", "review"}
VALID_STATUSES = ACTIVE_STATUSES | {"completed", "cancelled", "expired"}
VALID_TRANSITIONS = {
    "open": {"assigned", "cancelled", "expired"},
    "assigned": {"in_progress", "cancelled", "expired"},
    "in_progress": {"review", "cancelled", "expired"},
    "review": {"in_progress", "completed", "cancelled", "expired"},
    "completed": set(),
    "cancelled": set(),
    "expired": set(),
}


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str


def expire_if_deadline_passed(task: Task) -> bool:
    if task.deadline and task.status in ACTIVE_STATUSES and task.deadline < datetime.utcnow():
        task.status = "expired"
        task.updated_at = datetime.utcnow()
        return True
    return False


def validate_status_transition(task: Task, requested_status: str, user_id: int) -> None:
    if requested_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {requested_status}")
    if requested_status not in VALID_TRANSITIONS.get(task.status, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition task from {task.status} to {requested_status}",
        )
    if requested_status == "completed" and task.creator_id == user_id:
        raise HTTPException(status_code=403, detail="Task creator cannot complete their own task")


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
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
):
    query = db.query(Task)
    if status:
        query = query.filter(Task.status == status)
    if creator:
        query = query.filter(Task.creator_id == creator)
    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    changed = any(expire_if_deadline_passed(task) for task in tasks)
    if changed:
        db.commit()
    return tasks


@router.get("/{task_id}")
async def get_task(task_id: int, db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if expire_if_deadline_passed(task):
        db.commit()
        db.refresh(task)
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

    if expire_if_deadline_passed(task):
        db.commit()
        raise HTTPException(status_code=400, detail="Task deadline has expired")

    if task.creator_id != user["id"] and update.status != "completed":
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    validate_status_transition(task, update.status, user["id"])
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
    if expire_if_deadline_passed(task):
        db.commit()
        raise HTTPException(status_code=400, detail="Task deadline has expired")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")
    task.status = "cancelled"
    task.updated_at = datetime.utcnow()
    db.commit()
    return {"id": task.id, "status": "cancelled"}
