"""Webhook subscription endpoints and task state delivery helpers."""

import asyncio
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from ..middleware.auth import get_current_user
from ..models.database import get_db, Task, WebhookDelivery, WebhookSubscription

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

TASK_EVENTS = {"created", "assigned", "completed", "disputed"}


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: sorted(TASK_EVENTS))
    secret: Optional[str] = Field(default=None, min_length=16, max_length=128)


class WebhookUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    events: Optional[list[str]] = None
    active: Optional[bool] = None


def _validate_events(events: list[str]) -> list[str]:
    unknown = sorted(set(events) - TASK_EVENTS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported webhook events: {', '.join(unknown)}")
    return sorted(set(events))


def sign_payload(secret: str, payload: dict) -> tuple[str, bytes]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}", body


@router.post("/")
async def create_webhook(
    webhook: WebhookCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    subscription = WebhookSubscription(
        owner_id=user["id"],
        url=str(webhook.url),
        secret=webhook.secret or secrets.token_urlsafe(32),
        events=_validate_events(webhook.events),
        active=1,
        created_at=datetime.utcnow(),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return {
        "id": subscription.id,
        "url": subscription.url,
        "events": subscription.events,
        "active": bool(subscription.active),
        "secret": subscription.secret,
    }


@router.get("/")
async def list_webhooks(user=Depends(get_current_user), db=Depends(get_db)):
    subscriptions = db.query(WebhookSubscription).filter(
        WebhookSubscription.owner_id == user["id"]
    ).all()
    return [
        {"id": sub.id, "url": sub.url, "events": sub.events, "active": bool(sub.active)}
        for sub in subscriptions
    ]


@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: int,
    update: WebhookUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    subscription = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.owner_id == user["id"],
    ).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if update.url is not None:
        subscription.url = str(update.url)
    if update.events is not None:
        subscription.events = _validate_events(update.events)
    if update.active is not None:
        subscription.active = 1 if update.active else 0
    db.commit()
    return {"id": subscription.id, "url": subscription.url, "events": subscription.events, "active": bool(subscription.active)}


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    subscription = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.owner_id == user["id"],
    ).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook not found")
    subscription.active = 0
    db.commit()
    return {"id": subscription.id, "active": False}


def _matches_event(events: list[str], event: str) -> bool:
    return event in (events or [])


async def deliver_task_webhooks(task: Task, event: str, db, client: Optional[httpx.AsyncClient] = None) -> None:
    if event not in TASK_EVENTS:
        return

    subscriptions = [
        sub for sub in db.query(WebhookSubscription).filter(WebhookSubscription.active == 1).all()
        if _matches_event(sub.events, event)
    ]
    payload = {
        "event": event,
        "task": {
            "id": task.id,
            "status": task.status,
            "creator_id": task.creator_id,
            "agent_id": task.agent_id,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=5)

    try:
        for subscription in subscriptions:
            delivery = WebhookDelivery(
                subscription_id=subscription.id,
                task_id=task.id,
                event=event,
                status="pending",
                attempts=0,
                created_at=datetime.utcnow(),
            )
            db.add(delivery)
            db.flush()

            signature, body = sign_payload(subscription.secret, payload)
            for attempt in range(1, 6):
                delivery.attempts = attempt
                try:
                    response = await client.post(
                        subscription.url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-OpenAgents-Event": event,
                            "X-OpenAgents-Signature": signature,
                        },
                    )
                    response.raise_for_status()
                    delivery.status = "delivered"
                    delivery.delivered_at = datetime.utcnow()
                    delivery.last_error = None
                    break
                except Exception as exc:
                    delivery.status = "failed"
                    delivery.last_error = str(exc)
                    if attempt < 5:
                        await asyncio.sleep(0.1 * attempt)
            db.commit()
    finally:
        if owns_client:
            await client.aclose()
