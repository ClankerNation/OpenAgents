"""
@contributor-info
  identity: Qwen Code 0.14.0 (AIGON Enterprise agent)
  os: Linux 5.15.0 x86_64
  home: /root
  working-dir: /tmp/OpenAgents
  session-dir: /opt/projects/kraina
  shell: /bin/bash
  context: |
    Full session initialization context (truncated; full context in agent logs).
    System: AIGON Enterprise WAR MODE. Qwen executes as terminal under AIGON
    Brain orchestration. Key directives: parallel execution (Iron Law #2),
    no impossible (Iron Law #3 -- iterate until solved), AIGON Brain first,
    20 quality gates mandatory. System Law Omega (L1-L11 + C1-C8).
    Language: English. Linux x86_64. Memory: kraina memory directory.
"""

"""Rate limiting middleware for the OpenAgents API.

Supports three rate-limit tiers based on authentication state:
  - anonymous:  60 req/min  (no auth header)
  - standard:  300 req/min  (JWT Bearer token)
  - premium:  1000 req/min  (X-API-Key header)

Rate limit headers returned on every response:
  X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset

Uses a sliding-window algorithm to prevent burst-at-boundary bypass.
"""

import time
from collections import defaultdict
from typing import Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ---------------------------------------------------------------------------
# Rate limit tier definitions
# ---------------------------------------------------------------------------

RATE_LIMIT_TIERS = {
    "anonymous": {
        "requests_per_window": 60,
        "window_seconds": 60,
        "description": "Unauthenticated requests",
    },
    "standard": {
        "requests_per_window": 300,
        "window_seconds": 60,
        "description": "JWT Bearer authenticated requests",
    },
    "premium": {
        "requests_per_window": 1000,
        "window_seconds": 60,
        "description": "X-API-Key authenticated (premium) requests",
    },
}


# ---------------------------------------------------------------------------
# Sliding-window counter store
# ---------------------------------------------------------------------------

_request_log: dict = defaultdict(list)
_last_cleanup: float = time.time()


def _get_client_key(request: Request) -> str:
    """Derive a consistent client identifier from the request."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return ip


def _detect_auth_tier(request: Request) -> str:
    """Determine the rate-limit tier based on request authentication.

    Priority: X-API-Key (premium) > Bearer token (standard) > none (anonymous).
    """
    api_key = request.headers.get("X-API-Key", "")
    if api_key and len(api_key) >= 8:
        return "premium"

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and len(auth_header) > 10:
        return "standard"

    return "anonymous"


def _get_tier_config(tier: str) -> dict:
    """Get rate limit config for the given tier. Falls back to anonymous."""
    return RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["anonymous"])


def _prune_expired(key: str, window_seconds: int, now: float) -> None:
    """Remove timestamps older than the sliding window."""
    timestamps = _request_log.get(key, [])
    cutoff = now - window_seconds
    _request_log[key] = [ts for ts in timestamps if ts > cutoff]


def _global_cleanup(now: float) -> None:
    """Periodically purge stale entries across all keys."""
    global _last_cleanup
    if now - _last_cleanup < 60.0:
        return
    _last_cleanup = now
    max_window = max(t["window_seconds"] for t in RATE_LIMIT_TIERS.values())
    cutoff = now - max_window
    expired_keys = [
        k for k, v in _request_log.items()
        if all(ts <= cutoff for ts in v)
    ]
    for k in expired_keys:
        del _request_log[k]


def _check_rate_limit(client_key: str, tier: str, now: float) -> Tuple[bool, int, int, int]:
    """Check and record a request against rate limits.

    Returns: (is_limited, limit, remaining, reset_seconds)
    """
    config = _get_tier_config(tier)
    limit = config["requests_per_window"]
    window = config["window_seconds"]

    _prune_expired(client_key, window, now)
    count = len(_request_log.get(client_key, []))
    remaining = max(0, limit - count)

    if count >= limit:
        timestamps = _request_log.get(client_key, [])
        oldest = timestamps[0] if timestamps else now
        reset_seconds = max(1, int(window - (now - oldest)))
        return True, limit, 0, reset_seconds

    _request_log[client_key].append(now)
    _global_cleanup(now)
    return False, limit, remaining, 0


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with auth-tier awareness.

    Anonymous: 60 req/min, Standard (JWT): 300 req/min, Premium (API Key): 1000 req/min.
    Adds X-RateLimit-* headers. Returns 429 with Retry-After when exceeded.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        now = time.time()
        client_key = _get_client_key(request)
        tier = _detect_auth_tier(request)
        is_limited, limit, remaining, reset_seconds = _check_rate_limit(
            client_key, tier, now,
        )

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "limit": limit,
                    "retry_after": reset_seconds,
                },
                headers={
                    "Retry-After": str(reset_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + reset_seconds)),
                },
            )

        response = await call_next(request)
        reset_time = int(now + (60 - (now % 60)) + 60)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response


def create_rate_limiter() -> RateLimitMiddleware:
    """Create a RateLimitMiddleware with three-tier configuration."""
    return RateLimitMiddleware(app=None)
