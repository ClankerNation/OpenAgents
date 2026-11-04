# @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
# @platform-config Verbatim session instructions, first token to the task:
#   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
#   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
#   weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
#   report of what changed, what's verified, and what's left, never a replay of the process. No
#   filler, no restating the request back, no re-summarizing what you already said, no narrating
#   tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
#   because it's right, not because the user said it. Depth is earned."
#   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
#   a working artifact backed by real tool output — not a description of one. Do not stop after
#   writing a stub, a plan, or a single command. Keep working until you have actually exercised the
#   code or produced the requested result."
#   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
#   or plan to do without actually doing it."
#   "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
#   'done' means every named acceptance criterion is verified — never a plausible subset."
#   "external_state_verification: after any state-changing write to an external system, verify the
#   effect by reading back the exact target before claiming success."
#   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
#   read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
#   web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.
# @env os=windows arch=x86_64 home_dir=C:\Users\2
#   working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=C:\Program Files\Git\bin\bash.exe
# @timestamp 2026-11-04T14:40:00Z
# ---------------------------------------------------------------

"""Task management endpoints for bounty assignments."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user
from ..services.task_events import heartbeat_seconds, task_events

MAX_SUBSCRIPTIONS = 50

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
    await task_events.publish(new_task.id, "task.created", {"status": new_task.status})
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
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # BUG: Creator can mark their own task as completed — should require
    # a third party or the assignee to confirm completion
    # the JWT subject is a string, the column an int
    if str(task.creator_id) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    await task_events.publish(task.id, "task.status", {"status": task.status})
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if str(task.creator_id) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")
    task.status = "cancelled"
    db.commit()
    return {"id": task.id, "status": "cancelled"}


# --------------------------------------------------------------------------------------------
# Real-time task updates
# --------------------------------------------------------------------------------------------

async def _receive(ws: WebSocket) -> None:
    while True:
        try:
            message = await ws.receive_json()
        except ValueError:
            await ws.send_json({"type": "error", "detail": "frame is not JSON"})
            continue

        action = message.get("action")
        raw_ids = message.get("task_ids", [])
        if isinstance(raw_ids, (int, str)):
            raw_ids = [raw_ids]
        try:
            ids = [int(i) for i in raw_ids]
        except (TypeError, ValueError):
            await ws.send_json({"type": "error", "detail": "task_ids must be integers"})
            continue

        if action == "subscribe":
            current = task_events.subscribe(ws, ids[:MAX_SUBSCRIPTIONS])
            await ws.send_json({"type": "subscribed", "task_ids": current})
        elif action == "unsubscribe":
            current = task_events.unsubscribe(ws, ids)
            await ws.send_json({"type": "unsubscribed", "task_ids": current})
        elif action == "ping":
            await ws.send_json({"type": "pong"})
        elif action == "list":
            await ws.send_json({"type": "subscribed", "task_ids": task_events.subscribed(ws)})
        else:
            await ws.send_json({"type": "error", "detail": "unknown action"})


async def _send(ws: WebSocket, interval: float) -> None:
    conn = task_events
    while True:
        try:
            await asyncio.wait_for(conn.drain(ws), timeout=interval)
        except asyncio.TimeoutError:
            await ws.send_json({"type": "ping"})


@router.websocket("/ws")
async def task_updates(ws: WebSocket):
    """Subscribe with {"action":"subscribe","task_ids":[1,2]} and receive task events.

    Only subscribed ids are delivered. A ping frame goes out every HEARTBEAT_SECONDS (default 30)
    so idle connections are not reaped by proxies.
    """
    await ws.accept()
    task_events.register(ws)
    interval = heartbeat_seconds()
    await ws.send_json({"type": "hello", "heartbeat": interval})

    receiver = asyncio.create_task(_receive(ws))
    sender = asyncio.create_task(_send(ws, interval))
    try:
        await asyncio.wait({receiver, sender}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        task_events.unregister(ws)
        for pending in (receiver, sender):
            pending.cancel()
