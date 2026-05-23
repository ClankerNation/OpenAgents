"""Rate limiting middleware for the OpenAgents API."""

import time
import jwt
import os
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


# Tier limits: (requests per window, window seconds, burst)
TIERS = {
    "anonymous": (60, 60, 10),
    "authenticated": (300, 60, 50),
    "premium": (1000, 60, 100),
}

JWT_SECRET = os.getenv("JWT_SECRET", "default-secret")


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _determine_tier(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        return "premium"
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            roles = payload.get("roles", [])
            if "premium" in roles:
                return "premium"
            return "authenticated"
        except Exception:
            return "anonymous"
    return "anonymous"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_tier_limits(self, tier: str) -> tuple:
        return TIERS.get(tier, TIERS["anonymous"])

    def _check_rate_limit(self, client_ip: str, tier: str) -> Tuple[bool, int, int, int]:
        max_reqs, window, _ = self._get_tier_limits(tier)
        count, window_start = _request_counts[client_ip]
        now = time.time()

        if now - window_start >= window:
            _request_counts[client_ip] = (1, now)
            window_start = now
            count = 0

        reset_time = int(window_start + window)
        if count >= max_reqs:
            retry_after = int(window - (now - window_start))
            return True, retry_after, max_reqs, 0

        _request_counts[client_ip] = (count + 1, window_start)
        remaining = max_reqs - count - 1
        return False, remaining, max_reqs, reset_time

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier = _determine_tier(request)
        is_limited, value, limit, reset_time = self._check_rate_limit(client_ip, tier)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": value,
                },
                headers={
                    "Retry-After": str(value),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response


def create_rate_limiter() -> RateLimitMiddleware:
    return RateLimitMiddleware(app=None)
