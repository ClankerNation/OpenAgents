"""Webhook delivery helpers.

@contributor Codex Agent xyjk0511
@platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
@runtime Windows PowerShell, working directory F:/jiedan/OpenAgents-bounty-run
@date 2026-05-31T00:00:00-07:00
"""

import asyncio
import hmac
import hashlib
import json
from datetime import datetime
from typing import Any

import httpx

from ..models.database import WebhookDelivery, WebhookSubscription

WEBHOOK_EVENT_TYPES = {"created", "assigned", "completed", "disputed"}
MAX_WEBHOOK_ATTEMPTS = 5
BACKOFF_SECONDS = (1, 2, 4, 8)


def build_webhook_payload(task: Any, event_type: str) -> dict:
    return {
        "event": event_type,
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "creator_id": task.creator_id,
            "agent_id": task.agent_id,
            "reward_amount": task.reward_amount,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


def sign_payload(secret: str, payload: dict) -> str:
    body = serialize_payload(payload).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def serialize_payload(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


async def deliver_webhook(subscription: WebhookSubscription, delivery: WebhookDelivery, db) -> None:
    payload = delivery.payload
    body = serialize_payload(payload)
    signature = sign_payload(subscription.secret, payload)
    headers = {
        "Content-Type": "application/json",
        "X-OpenAgents-Event": delivery.event_type,
        "X-OpenAgents-Signature": f"sha256={signature}",
        "X-OpenAgents-Delivery": str(delivery.id),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(1, MAX_WEBHOOK_ATTEMPTS + 1):
            delivery.attempts = attempt
            try:
                response = await client.post(subscription.target_url, content=body, headers=headers)
                delivery.response_status = response.status_code
                delivery.response_body = response.text[:2048]
                if 200 <= response.status_code < 300:
                    delivery.status = "delivered"
                    delivery.delivered_at = datetime.utcnow()
                    delivery.error = None
                    db.commit()
                    return
                delivery.error = f"HTTP {response.status_code}"
            except Exception as exc:
                delivery.error = str(exc)

            delivery.status = "failed" if attempt == MAX_WEBHOOK_ATTEMPTS else "retrying"
            db.commit()
            if attempt < MAX_WEBHOOK_ATTEMPTS:
                await asyncio.sleep(BACKOFF_SECONDS[attempt - 1])


async def fire_task_webhooks(db, task: Any, event_type: str) -> None:
    if event_type not in WEBHOOK_EVENT_TYPES:
        return

    subscriptions = (
        db.query(WebhookSubscription)
        .filter(WebhookSubscription.active == 1)
        .all()
    )
    for subscription in subscriptions:
        if subscription.event_types and event_type not in subscription.event_types:
            continue
        payload = build_webhook_payload(task, event_type)
        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            task_id=task.id,
            event_type=event_type,
            payload=payload,
            status="pending",
            created_at=datetime.utcnow(),
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        await deliver_webhook(subscription, delivery, db)
