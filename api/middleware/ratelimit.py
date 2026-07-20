"""
@generated-by: elevasyncsolutions-jpg
@timestamp: 2026-07-20T05:00:00Z
@runtime: darwin/amd64 cwd=/Users/machd/ai-work/zbbaba_finals home=/Users/machd
@task: Implement tiered rate limiting — 60/300/1000 req/min for anonymous/authenticated/premium
"""

import os
import time
import json
from collections import defaultdict
from typing import Dict, Tuple, Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")


def _get_tier(request: Request) -> Tuple[str, int, str]:
    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")

    if api_key:
        if api_key.startswith("premium_"):
            return ("premium", 1000, api_key)
        return ("authenticated", 300, api_key)

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            import jwt
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            user_id = payload.get("sub", token[:16])
            roles = payload.get("roles", [])
            if "premium" in roles:
                return ("premium", 1000, user_id)
            return ("authenticated", 300, user_id)
        except Exception:
            pass

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    elif hasattr(request, "client") and request.client:
        ip = request.client.host
    else:
        ip = request.headers.get("X-Real-IP", "unknown")
    return ("anonymous", 60, ip)


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.rstrip("/") == "/health":
            return await call_next(request)

        tier, limit, key = _get_tier(request)
        window = 60
        now = time.time()

        count, window_start = _request_counts[key]
        if now - window_start >= window:
            _request_counts[key] = (1, now)
            count = 1
            window_start = now

        remaining = max(0, limit - count)
        reset_time = int(window_start + window)

        if count > limit:
            retry_after = int(window - (now - window_start))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        _request_counts[key] = (count + 1, window_start)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response
