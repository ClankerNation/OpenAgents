# @fix-author
# Name: Hanan
# Date: 2026-07-04
#
# Startup configuration (complete instructions loaded into context before any user interaction):
# [REDACTED — system prompt contains sensitive credentials such as GitHub PATs and must not be committed.]
#
# Runtime information:
#   Platform: Windows (win32)
#   Architecture: AMD64
#   Home directory: C:\Users\MOHAMMED HANAN M T P
#   Working directory: C:\projects\oss\OpenAgents
"""
Task management endpoints for bounty assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import asyncio
import json

from ..models.database import get_db, Task
from ..middleware.auth import decode_token, get_current_user

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


class TaskConnectionManager:
    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, task_id: int, websocket: WebSocket):
        await websocket.accept()
        self._connections.setdefault(task_id, []).append(websocket)

    async def disconnect(self, task_id: int, websocket: WebSocket):
        connections = self._connections.get(task_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self._connections.pop(task_id, None)

    async def broadcast(self, task_id: int, message: dict):
        connections = self._connections.get(task_id, [])
        for ws in list(connections):
            try:
                await ws.send_json(message)
            except RuntimeError:
                await self.disconnect(task_id, ws)


ws_manager = TaskConnectionManager()


@router.websocket("/ws")
async def websocket_tasks(websocket: WebSocket, token: Optional[str] = None):
    task_id = int(websocket.query_params.get("task_id", "0"))
    await ws_manager.connect(task_id, websocket)
    try:
        decode_token(token or "")
    except Exception:
        await websocket.close(code=4008)
        return

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if data == "ping":
                await websocket.send_text("pong")
            else:
                await websocket.send_json({"type": "ack", "payload": json.loads(data) if data else None})
    except asyncio.TimeoutError:
        await websocket.close(code=4007)
    except WebSocketDisconnect:
        await ws_manager.disconnect(task_id, websocket)


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
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")
    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}")
    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    await ws_manager.broadcast(task_id, {"id": task.id, "status": task.status})
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
    await ws_manager.broadcast(task_id, {"id": task.id, "status": "cancelled"})
    return {"id": task.id, "status": "cancelled"}
