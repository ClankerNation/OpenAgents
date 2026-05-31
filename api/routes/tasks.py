"""Task management endpoints for bounty assignments.

@contributor codex-gpt5
@platform Codex Desktop session bootstrap (platform-managed initialization context)
@runtime Windows 11 x64, cwd=F:/jiedan/OpenAgents
@date 2026-05-31T03:41:14Z
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task, User, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}


def _serialize_task(task: Task) -> dict:
    return {
        "id": task.uuid,
        "title": task.title,
        "description": task.description,
        "reward_amount": task.reward_amount,
        "status": task.status,
        "agent_id": task.agent.uuid if task.agent else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "deadline": task.deadline,
    }


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[str] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


@router.post("/")
async def create_task(task: TaskCreate, user=Depends(get_current_user), db=Depends(get_db)):
    agent_internal_id = None
    if task.agent_id:
        agent = db.query(Agent).filter(Agent.uuid == task.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent_internal_id = agent.id

    new_task = Task(
        title=task.title,
        description=task.description,
        reward_amount=task.reward_amount,
        creator_id=user["id"],
        agent_id=agent_internal_id,
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
        query = query.join(User, Task.creator_id == User.id).filter(User.uuid == creator)
    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    return [_serialize_task(task) for task in tasks]


@router.get("/{task_id}")
async def get_task(task_id: str, db=Depends(get_db)):
    task = db.query(Task).filter(Task.uuid == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _serialize_task(task)


@router.patch("/{task_id}/status")
async def update_task_status(
    task_id: str,
    update: TaskStatusUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    task = db.query(Task).filter(Task.uuid == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # BUG: Creator can mark their own task as completed — should require
    # a third party or the assignee to confirm completion
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return {"id": task.uuid, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.uuid == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")
    task.status = "cancelled"
    db.commit()
    return {"id": task.uuid, "status": "cancelled"}
