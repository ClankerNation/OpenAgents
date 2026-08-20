"""Webhook subscription management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from ..models.database import get_db, WebhookSubscription, WebhookDelivery
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENTS = {"created", "assigned", "completed", "disputed"}


class WebhookCreate(BaseModel):
    url: str
    events: List[str]
    secret: Optional[str] = None


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    active: Optional[bool] = None
    secret: Optional[str] = None


@router.post("/")
async def create_webhook(
    webhook: WebhookCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    # Validate events
    for event in webhook.events:
        if event not in VALID_EVENTS:
            raise HTTPException(status_code=400, detail=f"Invalid event: {event}")

    sub = WebhookSubscription(
        url=webhook.url,
        events=webhook.events,
        secret=webhook.secret,
        owner_id=user["id"],
        active=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"id": sub.id, "url": sub.url, "events": sub.events, "active": bool(sub.active)}


@router.get("/")
async def list_webhooks(
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    subs = db.query(WebhookSubscription).filter(
        WebhookSubscription.owner_id == user["id"]
    ).all()
    return [
        {
            "id": s.id,
            "url": s.url,
            "events": s.events,
            "active": bool(s.active),
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in subs
    ]


@router.get("/{webhook_id}")
async def get_webhook(
    webhook_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    sub = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.owner_id == user["id"],
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {
        "id": sub.id,
        "url": sub.url,
        "events": sub.events,
        "active": bool(sub.active),
        "secret": sub.secret,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: int,
    update: WebhookUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    sub = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.owner_id == user["id"],
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if update.url is not None:
        sub.url = update.url
    if update.events is not None:
        for event in update.events:
            if event not in VALID_EVENTS:
                raise HTTPException(status_code=400, detail=f"Invalid event: {event}")
        sub.events = update.events
    if update.active is not None:
        sub.active = 1 if update.active else 0
    if update.secret is not None:
        sub.secret = update.secret

    sub.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": sub.id, "url": sub.url, "events": sub.events, "active": bool(sub.active)}


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    sub = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.owner_id == user["id"],
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(sub)
    db.commit()
    return {"deleted": True}


@router.get("/{webhook_id}/deliveries")
async def list_deliveries(
    webhook_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    # Verify ownership
    sub = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.owner_id == user["id"],
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    deliveries = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == webhook_id)
        .order_by(WebhookDelivery.delivered_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": d.id,
            "event": d.event,
            "status_code": d.status_code,
            "success": bool(d.success),
            "attempts": d.attempts,
            "error_message": d.error_message,
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        }
        for d in deliveries
    ]
