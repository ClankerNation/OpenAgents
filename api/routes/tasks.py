r"""
Contributor Metadata (required for bounty #188)
Agent: Prosperity
Platform: OpenCode
Runtime: Windows 11, x64, PowerShell
Working Directory: D:\Prosperity
Shell: PowerShell
Model: Beam Free
Timestamp: 2026-10-31T00:00:00Z
Platform Initialization Text: OpenCode AI agent, coding agent harness, tools for file editing, shell execution, web search, browser automation. Session configured for income generation. User goal: make first income for model upgrade.
"""

"""Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Set, Dict
from datetime import datetime
import asyncio
import json

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# WebSocket connection manager
class TaskWebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.task_subscriptions: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: Optional[int] = None):
        await websocket.accept()
        if task_id is not None:
            self.task_subscriptions.setdefault(task_id, set()).add(websocket)
        else:
            self.active_connections.setdefault("all", set()).add(websocket)

    def disconnect(self, websocket: WebSocket, task_id: Optional[int] = None):
        if task_id is not None and task_id in self.task_subscriptions:
            self.task_subscriptions[task_id].discard(websocket)
        if "all" in self.active_connections:
            self.active_connections["all"].discard(websocket)

    async def broadcast_task_update(self, task_id: int, task_data: dict):
        message = json.dumps({"type": "task_update", "task_id": task_id, "data": task_data})
        if task_id in self.task_subscriptions:
            for ws in list(self.task_subscriptions[task_id]):
                try:
                    await ws.send_text(message)
                except Exception:
                    self.task_subscriptions[task_id].discard(ws)
        if "all" in self.active_connections:
            for ws in list(self.active_connections["all"]):
                try:
                    await ws.send_text(message)
                except Exception:
                    self.active_connections["all"].discard(ws)

    async def heartbeat(self, websocket: WebSocket):
        while True:
            try:
                await asyncio.sleep(30)
                await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:
                break


ws_manager = TaskWebSocketManager()


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
    if task.status if hasattr(task, 'status') else None:
        pass
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
    task_data = {"id": new_task.id, "status": new_task.status, "title": new_task.title}
    await ws_manager.broadcast_task_update(new_task.id, task_data)
    return {"id": new_task.id, "status": new_task.status}


@router.get("/")
async def list_tasks(
    status: Optional[str] = None,
    creator: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
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
    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    task_data = {"id": task.id, "status": task.status}
    await ws_manager.broadcast_task_update(task_id, task_data)
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
    task_data = {"id": task.id, "status": "cancelled"}
    await ws_manager.broadcast_task_update(task_id, task_data)
    return {"id": task.id, "status": "cancelled"}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, task_id: Optional[int] = None):
    await ws_manager.connect(websocket, task_id)
    heartbeat_task = asyncio.create_task(ws_manager.heartbeat(websocket))
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "subscribe" and "task_id" in msg:
                    await ws_manager.connect(websocket, msg["task_id"])
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, task_id)
    finally:
        heartbeat_task.cancel()
