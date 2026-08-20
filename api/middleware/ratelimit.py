# @contributor-info rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Rate limiting middleware for the OpenAgents API with tiered limits."""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitTier:
    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    PREMIUM = "premium"


TIER_LIMITS = {
    RateLimitTier.ANONYMOUS: 60,      # 60 req/min
    RateLimitTier.AUTHENTICATED: 300,  # 300 req/min
    RateLimitTier.PREMIUM: 1000,       # 1000 req/min
}

WINDOW_SECONDS = 60

# In-memory store: key -> (count, window_start)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_client_key(request: Request) -> str:
    """Get rate limit key from request. Uses IP for anonymous, user ID for authenticated."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    
    # Check for authenticated user in request state
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{ip}"


def _get_tier(request: Request) -> str:
    """Determine rate limit tier from request auth state."""
    # Check for premium API key
    api_key = request.headers.get("X-API-Key", "")
    if api_key.startswith("prem_"):
        return RateLimitTier.PREMIUM
    
    # Check for any valid authentication (JWT or API key)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") or api_key:
        return RateLimitTier.AUTHENTICATED
    
    return RateLimitTier.ANONYMOUS


def _is_rate_limited(key: str, limit: int) -> Tuple[bool, int, int]:
    """Check if key is rate limited. Returns (is_limited, remaining, retry_after)."""
    global _request_counts
    count, window_start = _request_counts[key]
    now = time.time()

    # Reset window if expired
    if now - window_start >= WINDOW_SECONDS:
        _request_counts[key] = (1, now)
        return False, limit - 1, 0

    if count >= limit:
        retry_after = int(WINDOW_SECONDS - (now - window_start)) + 1
        return True, 0, retry_after

    _request_counts[key] = (count + 1, window_start)
    remaining = limit - count - 1
    return False, remaining, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_key = _get_client_key(request)
        tier = _get_tier(request)
        limit = TIER_LIMITS[tier]
        
        is_limited, remaining, retry_after = _is_rate_limited(client_key, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMITED",
                    "message": "Rate limit exceeded",
                    "details": {"tier": tier, "limit": limit},
                    "request_id": getattr(request.state, "request_id", ""),
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + WINDOW_SECONDS)
        return response
