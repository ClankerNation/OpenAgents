/**
 * @contributor-info
 * Name: Karry2019web (Hermes Autonomous Agent)
 * Date: 2026-05-27
 * Session: Bounty hunter cron job — autonomous
 * Bounty: #122 ($3k) — UUID primary keys
 * Runtime: Windows 10, x86_64, git-bash
 * Platform: Hermes Agent (cron) — autonomous execution
 */

"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query
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
    return {"id": new_task.uuid, "status": new_task.status}


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
    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    return [{"id": t.uuid, "title": t.title, "status": t.status, "reward_amount": t.reward_amount, "created_at": t.created_at.isoformat() if t.created_at else None} for t in tasks]


@router.get("/{task_uuid}")
async def get_task(task_uuid: str, db=Depends(get_db)):
    task = db.query(Task).filter(Task.uuid == task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.uuid, "title": task.title, "description": task.description,
        "reward_amount": task.reward_amount, "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "deadline": task.deadline.isoformat() if task.deadline else None
    }


@router.patch("/{task_uuid}/status")
async def update_task_status(
    task_uuid: str,
    update: TaskStatusUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    task = db.query(Task).filter(Task.uuid == task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # BUG: Creator can mark their own task as completed — should require
    # a third party or the assignee to confirm completion
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    return {"id": task.uuid, "status": task.status}


@router.delete("/{task_uuid}")
async def cancel_task(task_uuid: str, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.uuid == task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")
    task.status = "cancelled"
    db.commit()
    return {"id": task.uuid, "status": "cancelled"}
