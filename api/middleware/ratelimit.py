# @fix-author rafaio1
# @date 2026-08-25T05:15:00Z
# @runtime linux x64 /tmp/openagents_issue_200 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for tiered rate limiting backwards compat (Issue #200)
"""Tiered rate limiting middleware for the OpenAgents API.

Implements sliding window counter with per-tier limits:
- Anonymous: 60 req/min
- Authenticated: 300 req/min
- Premium: 1000 req/min

Closes #200
"""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class ClientTier(Enum):
    """Represents the access tier for rate limiting purposes."""
    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    PREMIUM = "premium"


@dataclass(frozen=True)
class TierLimit:
    """Immutable configuration for a single rate limit tier."""
    requests_per_window: int
    window_seconds: int = 60


class SlidingWindowCounter:
    """Thread-safe sliding window rate limit counter."""

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets: Dict[str, Tuple[int, int, float]] = defaultdict(
            lambda: (0, 0, time.time())
        )

    def acquire(self, key: str, limit: TierLimit) -> Tuple[bool, int, int]:
        now = time.time()
        with self._lock:
            curr_count, prev_count, window_start = self._buckets[key]
            elapsed = now - window_start

            if elapsed >= limit.window_seconds * 2:
                self._buckets[key] = (1, 0, now)
                return True, limit.requests_per_window - 1, 0

            if elapsed >= limit.window_seconds:
                prev_count = curr_count
                curr_count = 0
                window_start += limit.window_seconds
                elapsed -= limit.window_seconds

            weight = 1.0 - (elapsed / limit.window_seconds)
            estimated = prev_count * weight + curr_count

            if estimated >= limit.requests_per_window:
                retry_after = max(1, int(limit.window_seconds - elapsed))
                self._buckets[key] = (curr_count, prev_count, window_start)
                return False, 0, retry_after

            new_count = curr_count + 1
            self._buckets[key] = (new_count, prev_count, window_start)
            remaining = max(0, limit.requests_per_window - int(estimated) - 1)
            return True, remaining, 0


TIER_LIMITS: Dict[ClientTier, TierLimit] = {
    ClientTier.ANONYMOUS: TierLimit(requests_per_window=60),
    ClientTier.AUTHENTICATED: TierLimit(requests_per_window=300),
    ClientTier.PREMIUM: TierLimit(requests_per_window=1000),
}

_counter = SlidingWindowCounter()


def _resolve_tier(request: Request) -> ClientTier:
    if request.headers.get("X-Premium-Access") == "true":
        return ClientTier.PREMIUM
    if request.headers.get("Authorization"):
        return ClientTier.AUTHENTICATED
    return ClientTier.ANONYMOUS


def _get_client_identifier(request: Request) -> str:
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware enforcing tiered sliding-window rate limits."""

    EXEMPT_PATHS = frozenset({"/health", "/healthz", "/ready"})

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        tier = _resolve_tier(request)
        limit = TIER_LIMITS[tier]
        identifier = _get_client_identifier(request)
        key = f"{tier.value}:{identifier}"

        allowed, remaining, retry_after = _counter.acquire(key, limit)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier.value,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit.requests_per_window),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                    "X-RateLimit-Tier": tier.value,
                },
            )

        response = await call_next(request)
        reset_time = int(time.time()) + limit.window_seconds
        response.headers["X-RateLimit-Limit"] = str(limit.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        response.headers["X-RateLimit-Tier"] = tier.value
        return response


def create_rate_limiter() -> RateLimitMiddleware:
    """Factory function for the tiered rate limit middleware."""
    return RateLimitMiddleware(app=None)
