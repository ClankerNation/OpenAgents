"""
@contributor doubao-agent (spiritwanghs fork)
@platform-config Autonomous coding agent executing GitHub bounties; user asked to do all available bounty issues.
@env os=linux arch=x64 home_dir=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=bash
@timestamp 2026-09-29T03:50:00Z
"""
"""Webhook dispatch: HMAC-SHA256 signed POSTs with retry/backoff."""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Optional

import httpx

from .models.database import WebhookSubscription, WebhookDelivery

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
# Exponential backoff in seconds: 1, 2, 4, 8, 16
BACKOFF_BASE = 1.0

EVENT_TYPES = {"created", "assigned", "completed", "disputed"}


def sign_payload(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def dispatch_webhook(
    db,
    subscription: WebhookSubscription,
    event: str,
    payload: dict,
    max_retries: int = MAX_RETRIES,
) -> WebhookDelivery:
    """POST a signed payload to a subscription with retry/backoff, and
    persist the delivery attempt history."""
    body = json.dumps(payload, default=str).encode()
    signature = sign_payload(subscription.secret, body)

    delivery = WebhookDelivery(
        subscription_id=subscription.id,
        event=event,
        payload=payload,
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(delivery)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Event": event,
    }

    attempt = 0
    last_error: Optional[str] = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        while attempt < max_retries:
            attempt += 1
            delivery.attempts = attempt
            try:
                resp = await client.post(subscription.url, content=body, headers=headers)
                if 200 <= resp.status_code < 300:
                    delivery.status = "success"
                    delivery.delivered_at = datetime.utcnow()
                    db.commit()
                    return delivery
                last_error = f"HTTP {resp.status_code}"
            except Exception as exc:  # noqa: BLE001 - record and retry
                last_error = str(exc)[:500]
            if attempt < max_retries:
                await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
            else:
                delivery.status = "failed"

    delivery.last_error = last_error
    db.commit()
    return delivery


async def fire_event(db, event: str, payload: dict) -> None:
    """Dispatch an event to all active subscriptions listening for it."""
    if event not in EVENT_TYPES:
        return
    subs = (
        db.query(WebhookSubscription)
        .filter(WebhookSubscription.active == 1)
        .all()
    )
    for sub in subs:
        if event in (sub.events or ["created", "assigned", "completed", "disputed"]):
            try:
                await dispatch_webhook(db, sub, event, payload)
            except Exception:  # noqa: BLE001 - one failing sub must not break others
                logger.exception("webhook dispatch failed for sub %s", sub.id)
