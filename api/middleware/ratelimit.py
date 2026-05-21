"""Rate limiting middleware for the OpenAgents API.

Provides three-tier rate limiting based on authentication state:
  - Anonymous:  60 requests/minute
  - Authenticated (JWT):  300 requests/minute
  - Premium (API key):  1000 requests/minute

Every response includes X-RateLimit-Limit, X-RateLimit-Remaining,
and X-RateLimit-Reset headers. 429 responses include Retry-After.

Contributor: iyop666 (https://github.com/iyop666)
"""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

TIER_ANONYMOUS = "anonymous"
TIER_AUTHENTICATED = "authenticated"
TIER_PREMIUM = "premium"

TIER_LIMITS: Dict[str, int] = {
    TIER_ANONYMOUS: 60,
    TIER_AUTHENTICATED: 300,
    TIER_PREMIUM: 1000,
}

WINDOW_SECONDS = 60


# ---------------------------------------------------------------------------
# In-memory store  (per-tier key:  "tier:identifier")
# ---------------------------------------------------------------------------

_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_tier(request: Request) -> str:
    """Determine the caller's rate-limit tier from the request.

    Priority:
      1. X-API-Key header  →  premium
      2. Authorization: Bearer <jwt>  →  authenticated
      3. Otherwise  →  anonymous
    """
    if request.headers.get("X-API-Key"):
        return TIER_PREMIUM

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 7:
        return TIER_AUTHENTICATED

    return TIER_ANONYMOUS


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return ip


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Health checks are exempt
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier = _classify_tier(request)
        limit = TIER_LIMITS[tier]
        client_ip = _client_key(request)
        store_key = f"{tier}:{client_ip}"

        is_limited, remaining, reset_ts = self._check(store_key, limit)

        if is_limited:
            retry_after = max(1, int(reset_ts - time.time()))
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
                    "X-RateLimit-Reset": str(int(reset_ts)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_ts))
        return response

    # ---- sliding-window counter -------------------------------------------

    @staticmethod
    def _check(key: str, limit: int) -> Tuple[bool, int, float]:
        """Return (is_limited, remaining, window_reset_epoch)."""
        count, window_start = _request_counts[key]
        now = time.time()

        if now - window_start >= WINDOW_SECONDS:
            _request_counts[key] = (1, now)
            return False, limit - 1, now + WINDOW_SECONDS

        if count >= limit:
            reset_ts = window_start + WINDOW_SECONDS
            return True, 0, reset_ts

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_ts = window_start + WINDOW_SECONDS
        return False, remaining, reset_ts


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_rate_limiter() -> RateLimitMiddleware:
    """Create a rate limiter with the default three-tier configuration."""
    return RateLimitMiddleware(app=None)
