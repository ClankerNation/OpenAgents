"""Task management endpoints for bounty assignments.

@contributor Codex Agent xyjk0511
@platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
@runtime Windows PowerShell, working directory F:/jiedan/OpenAgents-bounty-run
@date 2026-05-31T00:00:00-07:00
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Task, WebhookDelivery, WebhookSubscription
from ..middleware.auth import get_current_user
from ..services.webhooks import WEBHOOK_EVENT_TYPES, fire_task_webhooks

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"open", "assigned", "in_progress", "review", "completed", "cancelled", "disputed"}


class TaskCreate(BaseModel):
    title: str
    description: str
    reward_amount: float
    agent_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: str  # BUG: Not validated against VALID_STATUSES enum — any string accepted


class WebhookSubscriptionCreate(BaseModel):
    target_url: HttpUrl
    secret: str
    event_types: Optional[list[str]] = None


class WebhookSubscriptionUpdate(BaseModel):
    target_url: Optional[HttpUrl] = None
    secret: Optional[str] = None
    event_types: Optional[list[str]] = None
    active: Optional[bool] = None


def _validate_events(event_types: Optional[list[str]]) -> list[str]:
    if not event_types:
        return sorted(WEBHOOK_EVENT_TYPES)
    invalid = sorted(set(event_types) - WEBHOOK_EVENT_TYPES)
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid webhook events: {', '.join(invalid)}")
    return event_types


@router.post("/webhooks")
async def create_webhook_subscription(
    subscription: WebhookSubscriptionCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    new_subscription = WebhookSubscription(
        owner_id=user["id"],
        target_url=str(subscription.target_url),
        secret=subscription.secret,
        event_types=_validate_events(subscription.event_types),
        active=1,
        created_at=datetime.utcnow(),
    )
    db.add(new_subscription)
    db.commit()
    db.refresh(new_subscription)
    return {
        "id": new_subscription.id,
        "target_url": new_subscription.target_url,
        "event_types": new_subscription.event_types,
        "active": bool(new_subscription.active),
    }


@router.get("/webhooks")
async def list_webhook_subscriptions(user=Depends(get_current_user), db=Depends(get_db)):
    subscriptions = (
        db.query(WebhookSubscription)
        .filter(WebhookSubscription.owner_id == user["id"])
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "target_url": item.target_url,
            "event_types": item.event_types,
            "active": bool(item.active),
            "created_at": item.created_at,
        }
        for item in subscriptions
    ]


@router.patch("/webhooks/{subscription_id}")
async def update_webhook_subscription(
    subscription_id: int,
    update: WebhookSubscriptionUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    subscription = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.owner_id == user["id"],
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")

    if update.target_url is not None:
        subscription.target_url = str(update.target_url)
    if update.secret is not None:
        subscription.secret = update.secret
    if update.event_types is not None:
        subscription.event_types = _validate_events(update.event_types)
    if update.active is not None:
        subscription.active = 1 if update.active else 0
    subscription.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(subscription)
    return {
        "id": subscription.id,
        "target_url": subscription.target_url,
        "event_types": subscription.event_types,
        "active": bool(subscription.active),
    }


@router.delete("/webhooks/{subscription_id}")
async def delete_webhook_subscription(
    subscription_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    subscription = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.owner_id == user["id"],
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    db.delete(subscription)
    db.commit()
    return {"deleted": True}


@router.get("/webhooks/deliveries")
async def list_webhook_deliveries(
    subscription_id: Optional[int] = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(WebhookDelivery).join(WebhookSubscription).filter(
        WebhookSubscription.owner_id == user["id"]
    )
    if subscription_id is not None:
        query = query.filter(WebhookDelivery.subscription_id == subscription_id)
    deliveries = query.order_by(WebhookDelivery.created_at.desc()).limit(100).all()
    return [
        {
            "id": item.id,
            "subscription_id": item.subscription_id,
            "task_id": item.task_id,
            "event_type": item.event_type,
            "status": item.status,
            "attempts": item.attempts,
            "response_status": item.response_status,
            "error": item.error,
            "created_at": item.created_at,
            "delivered_at": item.delivered_at,
        }
        for item in deliveries
    ]


@router.post("/")
async def create_task(task: TaskCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_task = Task(
        title=task.title,
        description=task.description,
        reward_amount=task.reward_amount,
        creator_id=user["id"],
        agent_id=task.agent_id,
        status="assigned" if task.agent_id is not None else "open",
        created_at=datetime.utcnow(),
        deadline=task.deadline,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    await fire_task_webhooks(db, new_task, "created")
    if new_task.agent_id is not None:
        await fire_task_webhooks(db, new_task, "assigned")
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
    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid task status")

    # BUG: Creator can mark their own task as completed — should require
    # a third party or the assignee to confirm completion
    if task.creator_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the creator can update status")

    task.status = update.status
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    if update.status in WEBHOOK_EVENT_TYPES:
        await fire_task_webhooks(db, task, update.status)
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
