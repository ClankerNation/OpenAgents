"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user
from .admin import record_audit

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
async def create_task(
    task: TaskCreate,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
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
    db.flush()

    record_audit(
        db,
        action="task.create",
        actor_id=str(user["id"]),
        target_type="task",
        target_id=str(new_task.id),
        after_value={"title": task.title, "reward_amount": task.reward_amount},
        ip_address=request.client.host if request.client else None,
    )
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
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}/status")
async def update_task_status(
    task_id: int,
    update: TaskStatusUpdate,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    if update.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    before_status = task.status
    task.status = update.status
    task.updated_at = datetime.utcnow()

    record_audit(
        db,
        action="task.status_update",
        actor_id=str(user["id"]),
        target_type="task",
        target_id=str(task_id),
        before_value={"status": before_status},
        after_value={"status": update.status},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(
    task_id: int,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")

    before_status = task.status
    task.status = "cancelled"

    record_audit(
        db,
        action="task.cancel",
        actor_id=str(user["id"]),
        target_type="task",
        target_id=str(task_id),
        before_value={"status": before_status},
        after_value={"status": "cancelled"},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return {"id": task.id, "status": "cancelled"}
