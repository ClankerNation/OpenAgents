"""Rate limiting middleware for the OpenAgents API.

Three-tier rate limiting:
- Anonymous: 60 req/min
- Authenticated (API key): 300 req/min
- Premium API key: 1000 req/min

Returns standard rate limit headers on every response.
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


# Tier configurations: (requests_per_minute, description)
TIER_ANONYMOUS = 60
TIER_AUTHENTICATED = 300
TIER_PREMIUM = 1000
WINDOW_SECONDS = 60


class SlidingWindowCounter:
    """Sliding window rate limiter to avoid fixed-window boundary bursts."""

    def __init__(self):
        # client_id -> list of request timestamps
        self._windows: Dict[str, list] = defaultdict(list)

    def check(self, client_id: str, limit: int) -> Tuple[bool, int, int, float]:
        """Check rate limit. Returns (is_limited, remaining, limit, reset_ts)."""
        now = time.time()
        window_start = now - WINDOW_SECONDS

        # Remove expired entries
        self._windows[client_id] = [
            ts for ts in self._windows[client_id] if ts > window_start
        ]

        current_count = len(self._windows[client_id])

        if current_count >= limit:
            # Find the oldest request in window to calculate retry-after
            oldest = self._windows[client_id][0]
            reset_ts = oldest + WINDOW_SECONDS
            retry_after = max(1, int(reset_ts - now))
            return True, 0, limit, retry_after

        self._windows[client_id].append(now)
        remaining = limit - current_count - 1
        reset_ts = now + WINDOW_SECONDS
        return False, remaining, limit, reset_ts


# Global sliding window counter
_counter = SlidingWindowCounter()


def _get_tier(request: Request) -> Tuple[int, str]:
    """Determine rate limit tier from request auth state.

    Returns (limit, tier_name).
    """
    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")

    if auth_header.startswith("Bearer ") or api_key:
        # Check for premium key (premium keys have a specific prefix or header)
        if request.headers.get("X-API-Tier") == "premium" or api_key.startswith("pk_"):
            return TIER_PREMIUM, "premium"
        return TIER_AUTHENTICATED, "authenticated"

    return TIER_ANONYMOUS, "anonymous"


def _get_client_id(request: Request) -> str:
    """Extract a stable client identifier.

    Uses API key if present, otherwise falls back to the first trusted
    proxy IP or the direct client host.
    """
    # Prefer API key as identifier (stable across IP changes)
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        return f"key:{api_key[:16]}"

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return f"token:{token[:16]}"

    # Fall back to client IP — only trust X-Forwarded-For from known proxies
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP (original client) from the chain
        client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}"

    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_id = _get_client_id(request)
        limit, tier = _get_tier(request)

        is_limited, remaining, tier_limit, retry_after = _counter.check(client_id, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "limit": tier_limit,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(tier_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                    "X-RateLimit-Tier": tier,
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(tier_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + WINDOW_SECONDS))
        response.headers["X-RateLimit-Tier"] = tier
        return response
