"""Webhook delivery service for task state changes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime

import httpx

from ..models.database import WebhookSubscription, WebhookDelivery

TRACKED_EVENTS = {"created", "assigned", "completed", "disputed"}
MAX_RETRIES = 5


def _build_payload(task, event: str) -> dict:
    return {
        "event": event,
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "creator_id": task.creator_id,
            "agent_id": task.agent_id,
            "updated_at": (task.updated_at or task.created_at or datetime.utcnow()).isoformat(),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


def _sign_payload(secret: str, payload_bytes: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def _deliver_with_retries(
    db,
    subscription: WebhookSubscription,
    task_id: int,
    event: str,
    payload_bytes: bytes,
    headers: dict,
    client: httpx.AsyncClient,
    sleep=asyncio.sleep,
) -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        status_code = None
        body = None
        error_message = None
        success = False
        try:
            response = await client.post(
                subscription.target_url,
                content=payload_bytes,
                headers=headers,
                timeout=10.0,
            )
            status_code = response.status_code
            body = response.text[:2000]
            success = 200 <= response.status_code < 300
        except Exception as exc:
            error_message = str(exc)

        db.add(
            WebhookDelivery(
                subscription_id=subscription.id,
                task_id=task_id,
                event=event,
                attempt=attempt,
                success=success,
                status_code=status_code,
                response_body=body,
                error_message=error_message,
            )
        )
        db.commit()

        if success:
            return
        if attempt < MAX_RETRIES:
            await sleep(2 ** (attempt - 1))


async def notify_task_state_change(db, task, event: str) -> int:
    if event not in TRACKED_EVENTS:
        return 0

    subscriptions = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.creator_id == task.creator_id,
            WebhookSubscription.enabled.is_(True),
        )
        .all()
    )
    subscriptions = [s for s in subscriptions if event in (s.events or [])]
    if not subscriptions:
        return 0

    payload = _build_payload(task, event)
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    async with httpx.AsyncClient() as client:
        for subscription in subscriptions:
            headers = {
                "Content-Type": "application/json",
                "X-OpenAgents-Event": event,
                "X-OpenAgents-Signature": _sign_payload(subscription.secret, payload_bytes),
            }
            await _deliver_with_retries(
                db=db,
                subscription=subscription,
                task_id=task.id,
                event=event,
                payload_bytes=payload_bytes,
                headers=headers,
                client=client,
            )
    return len(subscriptions)
