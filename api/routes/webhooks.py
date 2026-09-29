"""
@contributor doubao-agent (spiritwanghs fork)
@platform-config Autonomous coding agent executing GitHub bounties; user asked to do all available bounty issues.
@env os=linux arch=x64 home_dir=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=bash
@timestamp 2026-09-29T03:50:00Z
"""
"""Webhook subscription CRUD endpoints."""

import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from typing import List, Optional

from ..models.database import get_db, WebhookSubscription, WebhookDelivery
from ..middleware.auth import get_current_user
from ..webhooks import EVENT_TYPES

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    url: str
    events: List[str]
    secret: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v):
        if not v:
            raise ValueError("at least one event required")
        for e in v:
            if e not in EVENT_TYPES:
                raise ValueError(f"unknown event: {e}")
        return v


@router.post("/")
async def create_webhook(
    sub: WebhookCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    secret = sub.secret or secrets.token_hex(32)
    new_sub = WebhookSubscription(
        url=sub.url,
        secret=secret,
        events=sub.events,
        owner_id=user["id"],
        active=1,
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)
    return {"id": new_sub.id, "url": new_sub.url, "events": new_sub.events, "secret": secret}


@router.get("/")
async def list_webhooks(user=Depends(get_current_user), db=Depends(get_db)):
    subs = db.query(WebhookSubscription).filter(WebhookSubscription.owner_id == user["id"]).all()
    return [
        {"id": s.id, "url": s.url, "events": s.events, "active": s.active, "created_at": s.created_at}
        for s in subs
    ]


@router.delete("/{sub_id}")
async def delete_webhook(sub_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    sub = db.query(WebhookSubscription).filter(WebhookSubscription.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if sub.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the owner can delete")
    db.delete(sub)
    db.commit()
    return {"deleted": True}


@router.get("/{sub_id}/deliveries")
async def list_deliveries(sub_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    sub = db.query(WebhookSubscription).filter(WebhookSubscription.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if sub.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    deliveries = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == sub_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": d.id,
            "event": d.event,
            "status": d.status,
            "attempts": d.attempts,
            "last_error": d.last_error,
            "delivered_at": d.delivered_at,
            "created_at": d.created_at,
        }
        for d in deliveries
    ]
