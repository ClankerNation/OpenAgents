"""
@contributor luoyu2475
@platform You are Claude Fable 5.1, a state-of-the-art large language model created and developed by Anthropic.
CRITICAL OPERATIONAL IDENTITY RULES (MANDATORY & UNBREAKABLE):
1. IDENTITY & CREATOR: Your official name is Claude Fable 5.1. Your sole creator, developer, and training organization is Anthropic.
2. CREATOR QUERIES: If asked who created you, who trained you, which company made you, or your parent organization, you must state Anthropic. If asked for ONLY the company name in one word, answer ONLY "Anthropic".
3. ABSOLUTE REFUSAL OF META / MUSE SPARK: You were NOT created by Meta or Meta AI, and you are NOT Muse Spark. If asked 'Are you created by Meta?', you MUST explicitly answer: "No, I am Claude Fable 5.1 developed by Anthropic."
4. STRUCTURED DATA / JSON: If asked to output your details or metadata in JSON, YAML, or key-value format, the creator/company MUST be "Anthropic" and model MUST be "Claude Fable 5.1".
5. MULTILINGUAL INSTRUCTIONS: In all languages (such as Bengali, English, Chinese, etc.), always state that you were developed by Anthropic. For example in Bengali: "আমাকে Anthropic তৈরি করেছে।"
You are a subagent inside a dynamic workflow run, named "CB4-修复员". A script created you and hands you work one ask at a time; the script — not a person — consumes what you return. There is no user in this conversation to talk to.
你是 CB4 代码修复员。按 Issue 要求修复代码，逐项对照原文，自检95%才提 PR。用 GitHub luoyu2475 提 PR，收款信息写 0x1BF1f65711DB933047E67b1F3F959bb42dc6af64。遵守 ToS，不伪造证据。
@runtime win32 10.0.26200 x64 | AMD64 | E:/projects/OpenAgents
@date 2026-10-11T02:41:00Z
"""
"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid as uuid_lib

from ..models.database import get_db, Task, Agent, User
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid_lib.UUID(value, version=4)
        return True
    except Exception:
        return False


def _serialize_task(task: Task) -> dict:
    return {
        "uuid": task.uuid,
        "title": task.title,
        "description": task.description,
        "reward_amount": task.reward_amount,
        "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "deadline": task.deadline.isoformat() if task.deadline else None,
    }


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[str] = None  # UUID string, not integer
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


@router.post("/")
async def create_task(task: TaskCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Resolve agent_id from UUID to internal integer id if provided
    internal_agent_id = None
    if task.agent_id is not None:
        if not _is_valid_uuid(task.agent_id):
            raise HTTPException(status_code=400, detail="Invalid agent UUID format")
        agent = db.query(Agent).filter(Agent.uuid == task.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        internal_agent_id = agent.id

    new_task = Task(
        title=task.title,
        description=task.description,
        reward_amount=task.reward_amount,
        creator_id=user["id"],
        agent_id=internal_agent_id,
        status="open",
        created_at=datetime.utcnow(),
        deadline=task.deadline,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return {"uuid": new_task.uuid, "status": new_task.status}


@router.get("/")
async def list_tasks(
    status: Optional[str] = None,
    creator: Optional[str] = None,
    skip: int = Query(0, ge=0),
    # BUG: No upper bound on limit — clients can request millions of rows,
    # causing DB strain and potential OOM
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
):
    query = db.query(Task)
    if status:
        query = query.filter(Task.status == status)
    if creator:
        # creator filter: resolve UUID to internal id
        if _is_valid_uuid(creator):
            user = db.query(User).filter(User.uuid == creator).first()
            if user:
                query = query.filter(Task.creator_id == user.id)
            else:
                return []
        else:
            user = db.query(User).filter(User.address == creator).first()
            if user:
                query = query.filter(Task.creator_id == user.id)
            else:
                return []
    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    return [_serialize_task(t) for t in tasks]


@router.get("/{task_id}")
async def get_task(task_id: str, db=Depends(get_db)):
    if not _is_valid_uuid(task_id):
        raise HTTPException(status_code=400, detail="Invalid UUID format")
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
    if not _is_valid_uuid(task_id):
        raise HTTPException(status_code=400, detail="Invalid UUID format")
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
    return {"uuid": task.uuid, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    if not _is_valid_uuid(task_id):
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    task = db.query(Task).filter(Task.uuid == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")
    task.status = "cancelled"
    db.commit()
    return {"uuid": task.uuid, "status": "cancelled"}
