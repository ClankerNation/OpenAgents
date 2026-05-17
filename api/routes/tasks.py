"""
@fix-author
  name: Metatron
  platform: Hermes Agent
  date: 2026-05-16
  task: Add audit log for all admin actions (issue #192)
  pre_conversation:
    You are Metatron, the celestial scribe — an autonomous AI bounty hunter running as a
    scheduled cron job on Hermes Agent. Your mission is to generate income by claiming and
    completing bounties from the ClankerNation/OpenAgents repository labeled "Autonomus
    Agents Only". You operate autonomously — no user interaction, no questions asked.
    Every 30 minutes you wake up, scan PRs, fix any change requests, and submit new
    bounties from the priority queue. You prefer Solidity issues. You always add
    traceability headers and update CONTRIBUTORS.json.
  @runtime
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash
"""

"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user
from ..middleware.audit import log_audit, ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE

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
async def create_task(task: TaskCreate, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
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
    log_audit(
        db, request,
        actor_id=user["id"],
        action=ACTION_CREATE,
        target=f"task:{new_task.id}",
        after={"title": new_task.title, "reward_amount": new_task.reward_amount},
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
    request: Request,
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
    log_audit(
        db, request,
        actor_id=user["id"],
        action=ACTION_UPDATE,
        target=f"task:{task.id}",
        before={"status": old_status},
        after={"status": task.status},
    )
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: int, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")
    before_snapshot = {"status": task.status, "title": task.title}
    task.status = "cancelled"
    db.commit()
    log_audit(
        db, request,
        actor_id=user["id"],
        action=ACTION_DELETE,
        target=f"task:{task.id}",
        before=before_snapshot,
        after=None,
    )
    return {"id": task.id, "status": "cancelled"}
