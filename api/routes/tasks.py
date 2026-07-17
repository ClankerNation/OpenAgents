# @contributor ahmedabdelkarim504-commits
# @platform-config Agent protocol: Read Brain Home.md first. Read E:\AiLab\Obsidian Vault\Brain Home.md on every prompt before planning, coding, or answering; infer project, path, and stack from Brain instead of asking the user to re-explain the workspace. NEVER DELETE ANYTHING WITHOUT EXPLICIT USER PERMISSION. No files, code, configurations, database records, vault notes, components, features, or any data may be deleted without the user explicitly requesting deletion. Always ask for confirmation before deleting. Prefer archiving, deprecating, or moving to a _deprecated/ folder over deletion. Agent Memory System (cross-session): Run agent_memory.py summary on session start. Vault RAG: Use vault_rag.py for context. Brain Home maps all projects: 3d-portfolio, 3d-portfolio-generator, ahmed-3d-portfolio, el-ostaz-project, Social media (TrendMaker), apexyard-main, Shannon pentest, nometa, maator-nextgen, matoor garage ERP, quantum-labs-website, kids-ai-teacher, Patrick my assistant, python tools for AI, sales-crm, fox-order-taker, chatbot-Qlabs-CS, wifi-radar-app, echomind-v2, bruno-simon-folio-2025. Disambiguation: portfolio->3D Portfolio, generator->3D Portfolio Generator, ahmed->Ahmed 3D Portfolio, ostaz->El Ostaz, trendmaker/nometa->Social media, shannon/pentest->AiLab root, bounty hunter/algora/superteam->Web3 Bounty Hunter->python tools for ai/web3_bounty_hunter/. Skill system: Use skill tool to load specialized skills when task matches. Available skills: ce-work, ce-code-review, ce-brainstorm, ce-plan, ce-commit, ce-debug, ce-frontend-design, etc. Brainstem: 1,963 tools via MCP. Video editor+montage: 5 suites, 46 actions, ffmpeg. Codebase search: Use SocratiCode MCP tools before speculative file reads.
# @env {"os": "win32", "arch": "x64", "home_dir": "C:\\Users\\SS", "working_dir": "E:\\AiLab", "shell": "powershell.exe"}
# @timestamp 2026-07-17T15:10:00Z

"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import re

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}
STATUS_TRANSITIONS = {
    "open": {"assigned", "cancelled"},
    "assigned": {"in_progress", "cancelled"},
    "in_progress": {"review", "cancelled"},
    "review": {"completed", "in_progress"},
    "completed": set(),
    "cancelled": set(),
}


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
    limit: int = Query(50, ge=1, le=100),  # FIX: Cap at 100
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

    # FIX: Validate status against allowed values
    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    # FIX: Validate status transition
    allowed_next = STATUS_TRANSITIONS.get(task.status, set())
    if update.status not in allowed_next:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{task.status}' to '{update.status}'"
        )

    # FIX: Creator cannot mark own task as completed — must be assignee or third party
    if update.status == "completed" and task.creator_id == user["id"]:
        raise HTTPException(status_code=403, detail="Creator cannot mark their own task as completed")

    # FIX: Deadline enforcement
    if task.deadline and datetime.utcnow() > task.deadline and task.status in ("assigned", "in_progress"):
        raise HTTPException(status_code=400, detail="Task deadline has passed")

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
