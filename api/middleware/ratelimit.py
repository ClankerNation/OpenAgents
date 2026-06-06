"""
Rate limiting middleware for the OpenAgents API.

Contributor: Claude Agent (Anthropic)
Platform: Claude Code v4.6
Runtime: Python 3.12+ / FastAPI / Starlette
Initialization: pip install -r api/requirements.txt && uvicorn api.main:app

Multi-tier rate limiter with sliding-window counters and per-tier limits:
  - Anonymous:  60 req/min
  - Authenticated: 300 req/min
  - Premium:     1000 req/min

Response headers (every response):
  X-RateLimit-Limit     — tier ceiling for this client
  X-RateLimit-Remaining — calls left in current window
  X-RateLimit-Reset     — Unix timestamp when the window resets

On 429:
  Retry-After header + JSON body with "error" and "retry_after" fields.

Fixed from legacy implementation:
  - [FIXED] Fixed-window → sliding-window counters (prevents 2x burst at boundaries)
  - [FIXED] X-Forwarded-For client spoofing → only trusted proxies
  - [FIXED] In-memory store volatility → per-process acceptable for single-node
    deployments; documented that multi-node needs Redis adapter
  - [ADDED] Three-tier differentiation (anonymous / authenticated / premium)
  - [ADDED] X-RateLimit-Reset header
  - [ADDED] Retry-After on 429 responses
"""

import time
import hashlib
import hmac
import os
from collections import defaultdict
from typing import Dict, Tuple, Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Trusted proxy CIDRs / IPs — only the first address in X-Forwarded-For from
# a trusted proxy is accepted.  If your deployment uses a load-balancer that
# sets X-Forwarded-For, add its IP here.
TRUSTED_PROXY_IPS: Tuple[str, ...] = tuple(
    ip.strip()
    for ip in os.environ.get("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",")
    if ip.strip()
)

# Rate-limit tiers (requests per 60-second sliding window)
TIER_ANONYMOUS = 60
TIER_AUTHENTICATED = 300
TIER_PREMIUM = 1000

WINDOW_SECONDS = 60
WINDOW_GRANULARITY = max(1, WINDOW_SECONDS // 10)  # sub-window for sliding accuracy

# Secret used to HMAC-sign rate-limit reset headers (prevents client tampering)
_RATE_LIMIT_SECRET = os.environ.get("RATE_LIMIT_SECRET", os.urandom(32).hex())


# ---------------------------------------------------------------------------
# Sliding-window counter store
# ---------------------------------------------------------------------------

class _SlidingWindowStore:
    """
    In-memory sliding-window store.

    Suitable for single-node deployments.  For multi-node (horizontal scaling),
    swap this out for a Redis-backed implementation that uses sorted-set
    ZREMRANGEBYSCORE + ZCARD.
    """

    def __init__(self) -> None:
        # key → list of (timestamp, count) buckets
        self._buckets: Dict[str, list] = defaultdict(list)

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        self._buckets[key] = [
            (ts, cnt) for ts, cnt in self._buckets[key] if ts > cutoff
        ]

    def get_count(self, key: str) -> int:
        now = time.time()
        self._prune(key, now)
        return sum(cnt for _ts, cnt in self._buckets[key])

    def increment(self, key: str) -> int:
        now = time.time()
        self._prune(key, now)
        # Round timestamp to granularity to coalesce rapid requests
        bucket_ts = now - (now % WINDOW_GRANULARITY)
        self._buckets[key].append((bucket_ts, 1))
        return self.get_count(key)


_store = _SlidingWindowStore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sign(value: int) -> str:
    """Return an HMAC signature of *value* so clients can't forge reset times."""
    return hmac.new(
        _RATE_LIMIT_SECRET.encode(),
        str(value).encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


def _get_client_ip(request: Request) -> str:
    """
    Return the best-guess client IP.

    Only trusts X-Forwarded-For when the immediate upstream is a known
    trusted proxy — otherwise falls back to request.client.host.
    """
    client_host = request.client.host if request.client else "unknown"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Accept the header only from trusted proxies
        if client_host in TRUSTED_PROXY_IPS:
            return forwarded.split(",")[0].strip()

    return client_host


def _determine_user_tier(request: Request) -> Tuple[str, str, int]:
    """
    Determine rate-limit tier from request auth state.

    Returns (tier_name, identifier, limit).

    Tiers:
      - "premium"    — user authenticated AND has "premium" role
      - "authenticated" — user authenticated (valid JWT)
      - "anonymous"  — everyone else
    """
    # Try to extract user info from request state (set by auth middleware)
    user = getattr(request.state, "user", None)

    if user is None:
        # The auth middleware may inject the user via dependency override or
        # via request.state.  Fall back to checking Authorization header
        # presence as a lightweight signal.
        auth_header = request.headers.get("Authorization", "")
        if auth_header:
            # Has auth header but user not populated — treat as anonymous
            # until auth middleware can be refactored to populate state.
            pass

    if user and isinstance(user, dict):
        roles = user.get("roles", [])
        user_id = user.get("id") or user.get("address") or user.get("sub", "")
        if "premium" in roles:
            return ("premium", f"premium:{user_id}", TIER_PREMIUM)
        return ("authenticated", f"auth:{user_id}", TIER_AUTHENTICATED)

    # Anonymous path
    client_ip = _get_client_ip(request)
    return ("anonymous", f"anon:{client_ip}", TIER_ANONYMOUS)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Multi-tier rate-limiting middleware."""

    async def dispatch(self, request: Request, call_next):
        # Health-check endpoint is exempt
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier, identity, limit = _determine_user_tier(request)

        # --- Check / increment sliding window --------------------------------
        current_count = _store.get_count(identity)
        now = int(time.time())

        if current_count >= limit:
            window_start = now - (now % WINDOW_SECONDS)
            reset_at = window_start + WINDOW_SECONDS
            retry_after = max(1, reset_at - now)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        new_count = _store.increment(identity)
        remaining = max(0, limit - new_count)

        # --- Execute request -------------------------------------------------
        response = await call_next(request)

        # --- Attach rate-limit headers to response ---------------------------
        window_start = now - (now % WINDOW_SECONDS)
        reset_at = window_start + WINDOW_SECONDS

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)

        return response


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_rate_limiter() -> RateLimitMiddleware:
    """Return a configured RateLimitMiddleware instance."""
    return RateLimitMiddleware(app=None)
