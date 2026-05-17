from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import secrets

from ..models.database import get_db, WebhookSubscription
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    url: str
    events: List[str]


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    active: Optional[bool] = None


@router.post("/")
async def create_webhook(
    wh: WebhookCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    secret = secrets.token_hex(32)
    sub = WebhookSubscription(
        user_id=user["id"],
        url=wh.url,
        secret=secret,
        events=wh.events,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {
        "id": sub.id,
        "url": sub.url,
        "events": sub.events,
        "secret": secret,
    }


@router.get("/")
async def list_webhooks(
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    subs = db.query(WebhookSubscription).filter(
        WebhookSubscription.user_id == user["id"]
    ).all()
    return [
        {
            "id": s.id,
            "url": s.url,
            "events": s.events,
            "active": s.active,
            "created_at": s.created_at.isoformat(),
        }
        for s in subs
    ]


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    sub = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == user["id"],
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(sub)
    db.commit()
    return {"deleted": True}


@router.put("/{webhook_id}")
async def update_webhook(
    webhook_id: int,
    update: WebhookUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    sub = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == user["id"],
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if update.url is not None:
        sub.url = update.url
    if update.events is not None:
        sub.events = update.events
    if update.active is not None:
        sub.active = "active" if update.active else "inactive"
    db.commit()
    return {"id": sub.id, "url": sub.url, "events": sub.events, "active": sub.active}
