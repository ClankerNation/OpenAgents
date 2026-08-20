"""Webhook notification service with HMAC signing and retry logic."""

import hashlib
import hmac
import json
import asyncio
from datetime import datetime
from typing import Optional
import httpx
from sqlalchemy.orm import Session
from ..models.database import WebhookSubscription, WebhookDelivery

MAX_RETRIES = 5
BASE_DELAY = 1.0  # seconds
MAX_DELAY = 60.0  # seconds


def sign_payload(payload: dict, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


async def deliver_webhook(
    db: Session,
    subscription: WebhookSubscription,
    event_type: str,
    payload: dict
) -> bool:
    """Deliver webhook with exponential backoff retry."""
    signed_payload = {
        "event": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "data": payload
    }
    
    signature = sign_payload(signed_payload, subscription.secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event_type,
        "X-Webhook-Delivery": str(subscription.id)
    }
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    subscription.url,
                    json=signed_payload,
                    headers=headers
                )
            
            delivery = WebhookDelivery(
                subscription_id=subscription.id,
                event_type=event_type,
                payload=signed_payload,
                response_status=response.status_code,
                success=1 if 200 <= response.status_code < 300 else 0,
                attempt=attempt,
                created_at=datetime.utcnow()
            )
            db.add(delivery)
            
            if 200 <= response.status_code < 300:
                subscription.last_delivery_at = datetime.utcnow()
                subscription.failure_count = 0
                db.commit()
                return True
            else:
                subscription.failure_count += 1
                db.commit()
                
        except Exception as e:
            delivery = WebhookDelivery(
                subscription_id=subscription.id,
                event_type=event_type,
                payload=signed_payload,
                response_status=None,
                success=0,
                attempt=attempt,
                created_at=datetime.utcnow()
            )
            db.add(delivery)
            subscription.failure_count += 1
            db.commit()
        
        if attempt < MAX_RETRIES:
            delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)
            await asyncio.sleep(delay)
    
    return False


async def notify_webhooks(
    db: Session,
    event_type: str,
    payload: dict
) -> int:
    """Notify all active subscriptions for an event type."""
    subscriptions = db.query(WebhookSubscription).filter(
        WebhookSubscription.active == 1
    ).all()
    
    delivered = 0
    for sub in subscriptions:
        events = sub.events or []
        if event_type in events or "*" in events:
            success = await deliver_webhook(db, sub, event_type, payload)
            if success:
                delivered += 1
    
    return delivered
