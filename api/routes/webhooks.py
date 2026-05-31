"""Webhook subscription CRUD and delivery history endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from ..middleware.auth import get_current_user
from ..models.database import get_db, WebhookSubscription, WebhookDelivery

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

ALLOWED_EVENTS = {"created", "assigned", "completed", "disputed"}


class WebhookCreate(BaseModel):
    target_url: HttpUrl
    secret: str = Field(min_length=8, max_length=128)
    events: list[str] = Field(default_factory=lambda: sorted(ALLOWED_EVENTS))
    enabled: bool = True


class WebhookUpdate(BaseModel):
    target_url: Optional[HttpUrl] = None
    secret: Optional[str] = Field(default=None, min_length=8, max_length=128)
    events: Optional[list[str]] = None
    enabled: Optional[bool] = None


def _validate_events(events: list[str]) -> list[str]:
    invalid = sorted(set(events) - ALLOWED_EVENTS)
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported events: {', '.join(invalid)}")
    return sorted(set(events))


@router.post("/")
async def create_webhook(subscription: WebhookCreate, user=Depends(get_current_user), db=Depends(get_db)):
    events = _validate_events(subscription.events)
    record = WebhookSubscription(
        creator_id=user["id"],
        target_url=str(subscription.target_url),
        secret=subscription.secret,
        events=events,
        enabled=subscription.enabled,
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "id": record.id,
        "target_url": record.target_url,
        "events": record.events,
        "enabled": record.enabled,
    }


@router.get("/")
async def list_webhooks(user=Depends(get_current_user), db=Depends(get_db)):
    records = (
        db.query(WebhookSubscription)
        .filter(WebhookSubscription.creator_id == user["id"])
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )
    return [
        {
            "id": record.id,
            "target_url": record.target_url,
            "events": record.events,
            "enabled": record.enabled,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        for record in records
    ]


@router.get("/{subscription_id}")
async def get_webhook(subscription_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    record = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.creator_id == user["id"],
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    return {
        "id": record.id,
        "target_url": record.target_url,
        "events": record.events,
        "enabled": record.enabled,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.patch("/{subscription_id}")
async def update_webhook(
    subscription_id: int,
    update: WebhookUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    record = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.creator_id == user["id"],
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")

    if update.target_url is not None:
        record.target_url = str(update.target_url)
    if update.secret is not None:
        record.secret = update.secret
    if update.events is not None:
        record.events = _validate_events(update.events)
    if update.enabled is not None:
        record.enabled = update.enabled
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return {
        "id": record.id,
        "target_url": record.target_url,
        "events": record.events,
        "enabled": record.enabled,
        "updated_at": record.updated_at,
    }


@router.delete("/{subscription_id}")
async def delete_webhook(subscription_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    record = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.creator_id == user["id"],
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    db.delete(record)
    db.commit()
    return {"id": subscription_id, "deleted": True}


@router.get("/{subscription_id}/deliveries")
async def list_deliveries(
    subscription_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    record = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.creator_id == user["id"],
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")

    deliveries = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == subscription_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": delivery.id,
            "task_id": delivery.task_id,
            "event": delivery.event,
            "attempt": delivery.attempt,
            "success": delivery.success,
            "status_code": delivery.status_code,
            "response_body": delivery.response_body,
            "error_message": delivery.error_message,
            "created_at": delivery.created_at,
        }
        for delivery in deliveries
    ]
