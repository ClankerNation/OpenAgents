"""Task management endpoints for bounty assignments."""

import asyncio
import json
from typing import Dict, Set

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
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
    status: str


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._all_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, task_id: Optional[int] = None):
        await websocket.accept()
        self._all_connections.add(websocket)
        if task_id is not None:
            if task_id not in self._connections:
                self._connections[task_id] = set()
            self._connections[task_id].add(websocket)

    def disconnect(self, websocket: WebSocket, task_id: Optional[int] = None):
        self._all_connections.discard(websocket)
        if task_id is not None and task_id in self._connections:
            self._connections[task_id].discard(websocket)

    async def broadcast(self, task_id: int, message: dict):
        targets = self._connections.get(task_id, set()) | self._all_connections
        dead = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def connection_count(self) -> int:
        return len(self._all_connections)


manager = ConnectionManager()


async def _heartbeat(ws: WebSocket):
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"type": "ping"})
    except Exception:
        pass


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket, task_id: Optional[int] = Query(None)):
    await manager.connect(websocket, task_id)
    heartbeat = asyncio.create_task(_heartbeat(websocket))
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "subscribe" and "task_id" in msg:
                tid = msg["task_id"]
                if tid not in manager._connections:
                    manager._connections[tid] = set()
                manager._connections[tid].add(websocket)
            elif msg.get("action") == "unsubscribe" and "task_id" in msg:
                tid = msg["task_id"]
                manager.disconnect(websocket, tid)
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat.cancel()
        manager.disconnect(websocket, task_id)


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
    await manager.broadcast(new_task.id, {
        "type": "task_created",
        "task_id": new_task.id,
        "status": new_task.status,
    })
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

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    await manager.broadcast(task_id, {
        "type": "task_status_changed",
        "task_id": task_id,
        "status": update.status,
    })
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
    await manager.broadcast(task_id, {
        "type": "task_status_changed",
        "task_id": task_id,
        "status": "cancelled",
    })
    return {"id": task.id, "status": "cancelled"}
