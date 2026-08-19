"""
Task management endpoints for bounty assignments.
@contributor ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
@timestamp 2026-08-19T02:50:00Z
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Set
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        self.client_subscriptions: Dict[WebSocket, Set[int]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.client_subscriptions[websocket] = set()

    def disconnect(self, websocket: WebSocket):
        subs = self.client_subscriptions.pop(websocket, set())
        for task_id in subs:
            if task_id in self.active_connections:
                self.active_connections[task_id].discard(websocket)
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]

    async def subscribe(self, websocket: WebSocket, task_id: int):
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)
        self.client_subscriptions[websocket].add(task_id)

    async def unsubscribe(self, websocket: WebSocket, task_id: int):
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        if websocket in self.client_subscriptions:
            self.client_subscriptions[websocket].discard(task_id)

    async def broadcast(self, task_id: int, message: dict):
        if task_id in self.active_connections:
            for connection in list(self.active_connections[task_id]):
                try:
                    await connection.send_json(message)
                except Exception:
                    self.disconnect(connection)


manager = ConnectionManager()


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
    limit: int = Query(50, ge=1, le=1000),
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

    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    if task.creator_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    
    await manager.broadcast(task.id, {
        "type": "task_update",
        "task_id": task.id,
        "status": task.status,
        "updated_at": task.updated_at.isoformat()
    })
    
    return {"id": task.id, "status": task.status}


@router.delete("/{task_id}")
async def cancel_task(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.creator_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if task.status not in ("open", "assigned"):
        raise HTTPException(status_code=400, detail="Cannot cancel an active task")
    task.status = "cancelled"
    task.updated_at = datetime.utcnow()
    db.commit()
    
    await manager.broadcast(task.id, {
        "type": "task_update",
        "task_id": task.id,
        "status": task.status,
        "updated_at": task.updated_at.isoformat()
    })
    
    return {"id": task.id, "status": "cancelled"}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping"})
        except Exception:
            pass

    heartbeat_task = asyncio.create_task(heartbeat())
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                task_id = msg.get("task_id")
                
                if action == "subscribe" and task_id is not None:
                    await manager.subscribe(websocket, int(task_id))
                    await websocket.send_json({"type": "subscribed", "task_id": int(task_id)})
                elif action == "unsubscribe" and task_id is not None:
                    await manager.unsubscribe(websocket, int(task_id))
                    await websocket.send_json({"type": "unsubscribed", "task_id": int(task_id)})
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        manager.disconnect(websocket)
