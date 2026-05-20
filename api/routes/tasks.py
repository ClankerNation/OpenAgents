"""Task management endpoints for bounty assignments.

Contributor metadata:
agent name: openai-codex-goalie
platform initialization text: Public user-provided substitute text only:
"You are a bankrupt developer who will be evicted if you cannot pay rent.
Find legal coding-agent work and earn rent."
runtime environment: OS=Linux, arch=x86_64,
cwd=/home/goalie/bounty_work/OpenAgents, shell=bash
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..middleware.auth import get_current_user
from ..models.database import Task, get_db

router = APIRouter(prefix="/tasks", tags=["tasks"])

MAX_PAGE_LIMIT = 100
ACTIVE_STATUSES = {"open", "assigned", "in_progress", "review"}
TERMINAL_STATUSES = {"completed", "cancelled", "expired"}
VALID_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES
VALID_TRANSITIONS = {
    "open": {"assigned", "cancelled"},
    "assigned": {"in_progress", "review", "completed", "cancelled"},
    "in_progress": {"review", "completed", "cancelled"},
    "review": {"in_progress", "completed", "cancelled"},
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


def _utcnow() -> datetime:
    return datetime.utcnow()


def _to_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _is_deadline_due(deadline: Optional[datetime], now: datetime) -> bool:
    normalized = _to_utc_naive(deadline)
    return bool(normalized and normalized <= now)


def _same_user(left, right) -> bool:
    return str(left) == str(right)


def _normalize_status(status: str) -> str:
    return status.strip().lower()


def _normalize_limit(limit: int) -> int:
    return min(limit, MAX_PAGE_LIMIT)


def _validate_status(status: str) -> str:
    normalized = _normalize_status(status)
    if normalized not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid task status")
    return normalized


def _expire_overdue_tasks(db, now: Optional[datetime] = None) -> bool:
    now = now or _utcnow()
    overdue_tasks = (
        db.query(Task)
        .filter(Task.status.in_(ACTIVE_STATUSES))
        .filter(Task.deadline.isnot(None))
        .all()
    )
    changed = False
    for task in overdue_tasks:
        if _is_deadline_due(task.deadline, now):
            task.status = "expired"
            task.updated_at = now
            changed = True
    return changed


def _ensure_not_expired(task: Task, db) -> None:
    if task.status == "expired":
        raise HTTPException(
            status_code=400,
            detail="Task deadline has expired",
        )
    now = _utcnow()
    if _is_deadline_due(task.deadline, now) and task.status in ACTIVE_STATUSES:
        task.status = "expired"
        task.updated_at = now
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Task deadline has expired",
        )


def _validate_transition(current_status: str, next_status: str) -> None:
    allowed = VALID_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot transition task from {current_status} "
                f"to {next_status}"
            ),
        )


def _can_user_complete_task(task: Task, user_id) -> bool:
    if _same_user(task.creator_id, user_id):
        return False
    if task.agent_id is None:
        return True
    agent = task.agent
    return bool(agent and _same_user(agent.owner_id, user_id))


def _commit_if_changed(db, changed: bool) -> None:
    if changed:
        db.commit()


@router.post("/")
async def create_task(
    task: TaskCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    deadline = _to_utc_naive(task.deadline)
    if _is_deadline_due(deadline, _utcnow()):
        raise HTTPException(
            status_code=400,
            detail="Task deadline must be in the future",
        )

    new_task = Task(
        title=task.title,
        description=task.description,
        reward_amount=task.reward_amount,
        creator_id=user["id"],
        agent_id=task.agent_id,
        status="open",
        created_at=_utcnow(),
        deadline=deadline,
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
    limit: int = Query(50, ge=1),
    db=Depends(get_db),
):
    normalized_status = _validate_status(status) if status else None
    changed = _expire_overdue_tasks(db)
    _commit_if_changed(db, changed)

    query = db.query(Task)
    if normalized_status:
        query = query.filter(Task.status == normalized_status)
    if creator:
        query = query.filter(Task.creator_id == creator)
    return (
        query.order_by(Task.created_at.desc())
        .offset(skip)
        .limit(_normalize_limit(limit))
        .all()
    )


@router.get("/{task_id}")
async def get_task(task_id: int, db=Depends(get_db)):
    changed = _expire_overdue_tasks(db)
    _commit_if_changed(db, changed)

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

    next_status = _validate_status(update.status)
    _ensure_not_expired(task, db)
    _validate_transition(task.status, next_status)

    if next_status == "completed":
        if not _can_user_complete_task(task, user["id"]):
            raise HTTPException(
                status_code=403,
                detail="Task creator cannot complete their own task",
            )
    elif not _same_user(task.creator_id, user["id"]):
        raise HTTPException(
            status_code=403,
            detail="Only the creator can update status",
        )

    task.status = next_status
    task.updated_at = _utcnow()
    db.commit()
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(
    task_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _same_user(task.creator_id, user["id"]):
        raise HTTPException(
            status_code=403,
            detail="Only the creator can cancel",
        )
    _ensure_not_expired(task, db)
    if task.status not in ("open", "assigned"):
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel an active task",
        )
    task.status = "cancelled"
    task.updated_at = _utcnow()
    db.commit()
    return {"id": task.id, "status": "cancelled"}
