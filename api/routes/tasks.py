# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow

"""Task management endpoints for bounty assignments with WebSocket support."""

import asyncio
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Set, Dict
from datetime import datetime

from ..models.database import get_db, Task
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}

# WebSocket connection manager for real-time task updates
class ConnectionManager:
    def __init__(self):
        # Map of task_id -> set of active websocket connections
        self.task_subscribers: Dict[int, Set[WebSocket]] = {}
        # Map of websocket -> set of subscribed task_ids
        self.client_subscriptions: Dict[WebSocket, Set[int]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.client_subscriptions[websocket] = set()

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            subscriptions = self.client_subscriptions.pop(websocket, set())
            for task_id in subscriptions:
                if task_id in self.task_subscribers:
                    self.task_subscribers[task_id].discard(websocket)
                    if not self.task_subscribers[task_id]:
                        del self.task_subscribers[task_id]

    async def subscribe(self, websocket: WebSocket, task_id: int):
        async with self._lock:
            if task_id not in self.task_subscribers:
                self.task_subscribers[task_id] = set()
            self.task_subscribers[task_id].add(websocket)
            self.client_subscriptions[websocket].add(task_id)

    async def unsubscribe(self, websocket: WebSocket, task_id: int):
        async with self._lock:
            if task_id in self.task_subscribers:
                self.task_subscribers[task_id].discard(websocket)
                if not self.task_subscribers[task_id]:
                    del self.task_subscribers[task_id]
            if websocket in self.client_subscriptions:
                self.client_subscriptions[websocket].discard(task_id)

    async def broadcast_task_update(self, task_id: int, event_type: str, data: dict):
        async with self._lock:
            subscribers = list(self.task_subscribers.get(task_id, set()))
        
        message = json.dumps({
            "event": event_type,
            "task_id": task_id,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        disconnected = []
        for ws in subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        
        # Clean up disconnected clients
        for ws in disconnected:
            await self.disconnect(ws)


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
    
    # Broadcast task creation
    await manager.broadcast_task_update(new_task.id, "task_created", {
        "title": new_task.title,
        "status": new_task.status,
        "creator_id": new_task.creator_id,
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
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    old_status = task.status
    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    
    # Broadcast status change to subscribers
    await manager.broadcast_task_update(task_id, "status_updated", {
        "old_status": old_status,
        "new_status": update.status,
        "updated_at": task.updated_at.isoformat(),
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
    
    old_status = task.status
    task.status = "cancelled"
    db.commit()
    
    # Broadcast cancellation
    await manager.broadcast_task_update(task_id, "task_cancelled", {
        "old_status": old_status,
        "cancelled_at": datetime.utcnow().isoformat(),
    })
    
    return {"id": task.id, "status": "cancelled"}


@router.websocket("/ws")
async def task_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates.
    
    Protocol:
    - Client sends: {"action": "subscribe", "task_id": 123}
    - Client sends: {"action": "unsubscribe", "task_id": 123}
    - Server sends: {"event": "status_updated", "task_id": 123, "data": {...}, "timestamp": "..."}
    - Server sends: {"event": "heartbeat", "timestamp": "..."} every 30s
    """
    await manager.connect(websocket)
    
    async def heartbeat():
        """Send periodic heartbeat to keep connection alive."""
        while True:
            try:
                await asyncio.sleep(30)
                await websocket.send_text(json.dumps({
                    "event": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat(),
                }))
            except Exception:
                break
    
    heartbeat_task = asyncio.create_task(heartbeat())
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")
                task_id = message.get("task_id")
                
                if action == "subscribe" and task_id is not None:
                    await manager.subscribe(websocket, int(task_id))
                    await websocket.send_text(json.dumps({
                        "event": "subscribed",
                        "task_id": task_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    }))
                elif action == "unsubscribe" and task_id is not None:
                    await manager.unsubscribe(websocket, int(task_id))
                    await websocket.send_text(json.dumps({
                        "event": "unsubscribed",
                        "task_id": task_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    }))
                else:
                    await websocket.send_text(json.dumps({
                        "event": "error",
                        "message": "Invalid message format. Use {action: subscribe|unsubscribe, task_id: number}",
                    }))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "message": "Invalid JSON",
                }))
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(websocket)
