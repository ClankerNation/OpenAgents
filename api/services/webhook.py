import hashlib
import hmac
import json
import asyncio
from typing import Optional
from datetime import datetime
from uuid import uuid4

import httpx


async def send_webhook(
    url: str,
    secret: str,
    event: str,
    payload: dict,
    max_retries: int = 5,
) -> bool:
    body = json.dumps({
        "event": event,
        "timestamp": datetime.utcnow().isoformat(),
        "id": str(uuid4()),
        "data": payload,
    }).encode()

    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Event": event,
    }

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, content=body, headers=headers)
                if resp.status_code < 500:
                    return True
        except (httpx.TimeoutException, httpx.RequestError):
            pass

        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)

    return False
