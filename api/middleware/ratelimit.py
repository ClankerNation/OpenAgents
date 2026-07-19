# @generated-by: elevateasyncsolutions-jpg
# Timestamp: 2026-07-20T12:00:00Z
# Startup-config: You are an expert Python/FastAPI engineer. Implement tiered rate limiting
# that differentiates anonymous vs authenticated users. Use in-memory counters keyed by
# client IP for anonymous and by user ID for authenticated. Rate limit headers in every
# response. Retry-After on 429. Three tiers: anonymous=60, authenticated=300, premium=1000
# req/min. Keep @generated-by doc block per project convention.
# Runtime: darwin/arm64, home=/Users/machd, cwd=/tmp/clanker/OpenAgents

"""Rate limiting middleware for the OpenAgents API with tier-based limits."""

import time
import jwt
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


TIERS = {
    "anonymous": {"limit": 60, "window": 60},
    "authenticated": {"limit": 300, "window": 60},
    "premium": {"limit": 1000, "window": 60},
}

_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_tier_from_request(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return "anonymous"
    try:
        payload = jwt.decode(
            auth.replace("Bearer ", ""),
            options={"verify_signature": False},
        )
        roles = payload.get("roles", [])
        if "premium" in roles:
            return "premium"
        if payload.get("sub"):
            return "authenticated"
    except jwt.InvalidTokenError:
        pass
    return "anonymous"


def _get_client_key(request: Request, tier: str) -> str:
    if tier == "anonymous":
        return _ip_key(request)
    auth = request.headers.get("Authorization", "")
    try:
        payload = jwt.decode(
            auth.replace("Bearer ", ""),
            options={"verify_signature": False},
        )
        sub = payload.get("sub")
        if sub:
            return f"user:{sub}"
    except jwt.InvalidTokenError:
        pass
    return _ip_key(request)


def _ip_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier = _get_tier_from_request(request)
        client_key = _get_client_key(request, tier)
        config = TIERS[tier]
        limit = config["limit"]
        window = config["window"]
        now = time.time()

        count, window_start = _request_counts[client_key]

        if now - window_start >= window:
            _request_counts[client_key] = (1, now)
            reset_time = int(now + window)
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(limit - 1)
            response.headers["X-RateLimit-Reset"] = str(reset_time)
            return response

        if count >= limit:
            retry_after = int(window - (now - window_start))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "limit": limit,
                    "remaining": 0,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(window_start + window)),
                },
            )

        _request_counts[client_key] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_time = int(window_start + window)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response
