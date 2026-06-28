"""
Rate limiting middleware for the OpenAgents API.

Tiered rate limiting:
- Anonymous: 60 req/min
- Authenticated (valid JWT): 300 req/min
- Premium (X-API-Key header): 1000 req/min
"""

import time
import os
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional
import jwt

# Premium API keys — in production, store in database
PREMIUM_API_KEYS = set(filter(None, [
    os.environ.get("PREMIUM_API_KEY_1"),
    os.environ.get("PREMIUM_API_KEY_2"),
]))

# Rate limit tiers (requests per minute)
RATE_LIMITS = {
    "anonymous": 60,
    "authenticated": 300,
    "premium": 1000,
}

WINDOW_SECONDS = 60

JWT_SECRET = os.environ.get("JWT_SECRET", "")


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_auth_tier(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in PREMIUM_API_KEYS:
        return "premium"

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return "authenticated"
        except jwt.InvalidTokenError:
            pass

    return "anonymous"


# In-memory store: key = (client_ip, tier)
_request_counts: Dict[Tuple[str, str], Tuple[int, float]] = defaultdict(
    lambda: (0, time.time())
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = _get_client_ip(request)
        tier = _get_auth_tier(request)
        limit = RATE_LIMITS[tier]

        key = (client_ip, tier)
        count, window_start = _request_counts[key]
        now = time.time()

        if now - window_start >= WINDOW_SECONDS:
            _request_counts[key] = (1, now)
            remaining = limit - 1
            reset_at = int(window_start + WINDOW_SECONDS)
        elif count >= limit:
            retry_after = int(WINDOW_SECONDS - (now - window_start))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                    "tier": tier,
                },
                headers={"Retry-After": str(retry_after)},
            )
        else:
            _request_counts[key] = (count + 1, window_start)
            remaining = limit - count - 1
            reset_at = int(window_start + WINDOW_SECONDS)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response


def create_rate_limiter() -> RateLimitMiddleware:
    return RateLimitMiddleware(app=None)
