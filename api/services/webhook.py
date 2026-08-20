"""Webhook notification system for task state changes."""

import hmac
import hashlib
import json
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from ..models.database import Base, WebhookSubscription, WebhookDelivery

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "openagents-webhook-secret-key")
MAX_RETRIES = 5
BACKOFF_BASE = 2  # seconds


def generate_signature(payload: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def deliver_webhook(
    url: str,
    event: str,
    payload: dict,
    subscription_id: int,
    db: Session,
):
    """Deliver webhook with retry logic and backoff."""
    body = json.dumps({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }).encode()

    signature = generate_signature(body, WEBHOOK_SECRET)
    headers = {
        "Content-Type": "application/json",
        "X-OpenAgents-Signature": f"sha256={signature}",
        "X-OpenAgents-Event": event,
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, content=body, headers=headers)

                delivery = WebhookDelivery(
                    subscription_id=subscription_id,
                    event=event,
                    payload=payload,
                    status_code=response.status_code,
                    success=200 <= response.status_code < 300,
                    attempts=attempt + 1,
                    delivered_at=datetime.now(timezone.utc),
                )
                db.add(delivery)
                db.commit()

                if 200 <= response.status_code < 300:
                    return True

                last_error = f"HTTP {response.status_code}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(BACKOFF_BASE ** (attempt + 1))

    # Final failure record
    delivery = WebhookDelivery(
        subscription_id=subscription_id,
        event=event,
        payload=payload,
        status_code=0,
        success=False,
        attempts=MAX_RETRIES,
        error_message=last_error,
        delivered_at=datetime.now(timezone.utc),
    )
    db.add(delivery)
    db.commit()
    return False


async def notify_task_state_change(
    db: Session,
    task_id: int,
    event: str,
    task_data: dict,
):
    """Notify all active webhook subscriptions about a task state change."""
    subscriptions = db.query(WebhookSubscription).filter(
        WebhookSubscription.active == True,
        WebhookSubscription.events.contains(event),
    ).all()

    tasks = []
    for sub in subscriptions:
        tasks.append(deliver_webhook(sub.url, event, task_data, sub.id, db))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
