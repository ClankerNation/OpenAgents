"""Webhook subscription management endpoints."""

import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from ..models.database import get_db, WebhookSubscription
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENTS = {"task.created", "task.updated", "task.completed", "payment.released", "*"}


class WebhookCreate(BaseModel):
    url: str
    events: list[str]
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v
    
    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        for event in v:
            if event not in VALID_EVENTS:
                raise ValueError(f"Invalid event: {event}. Valid: {VALID_EVENTS}")
        return v


class WebhookResponse(BaseModel):
    id: int
    url: str
    events: list[str]
    active: bool
    created_at: datetime
    last_delivery_at: Optional[datetime]


@router.post("/", response_model=WebhookResponse)
async def create_webhook(
    webhook: WebhookCreate,
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Create a new webhook subscription with auto-generated HMAC secret."""
    secret = secrets.token_hex(32)
    
    sub = WebhookSubscription(
        user_id=user["id"],
        url=webhook.url,
        secret=secret,
        events=webhook.events,
        active=1,
        created_at=datetime.utcnow()
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    
    return {
        "id": sub.id,
        "url": sub.url,
        "events": sub.events,
        "active": bool(sub.active),
        "created_at": sub.created_at,
        "last_delivery_at": sub.last_delivery_at,
        "secret": secret  # Only returned on creation
    }


@router.get("/", response_model=list[WebhookResponse])
async def list_webhooks(
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    """List all webhook subscriptions for the authenticated user."""
    subs = db.query(WebhookSubscription).filter(
        WebhookSubscription.user_id == user["id"]
    ).all()
    
    return [{
        "id": s.id,
        "url": s.url,
        "events": s.events,
        "active": bool(s.active),
        "created_at": s.created_at,
        "last_delivery_at": s.last_delivery_at
    } for s in subs]


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Delete a webhook subscription."""
    sub = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == user["id"]
    ).first()
    
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    db.delete(sub)
    db.commit()
    return {"deleted": True}
