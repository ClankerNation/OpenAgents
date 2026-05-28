"""Rate limiting middleware for the OpenAgents API.

Tiered rate limits:
  - Anonymous:       60 req/min
  - Authenticated:  300 req/min
  - Premium:       1000 req/min
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, List, Optional, Tuple
import jwt
import os


# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

class TierConfig:
    """Configuration for a single rate-limit tier."""

    __slots__ = ("name", "requests_per_window", "window_seconds")

    def __init__(self, name: str, requests_per_window: int, window_seconds: int = 60):
        self.name = name
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds


# Default tiers — callers may override via RateLimitConfig
ANONYMOUS_TIER = TierConfig("anonymous", requests_per_window=60)
AUTHENTICATED_TIER = TierConfig("authenticated", requests_per_window=300)
PREMIUM_TIER = TierConfig("premium", requests_per_window=1000)


class RateLimitConfig:
    def __init__(
        self,
        anonymous: Optional[TierConfig] = None,
        authenticated: Optional[TierConfig] = None,
        premium: Optional[TierConfig] = None,
        # Legacy kwargs — kept for backward compat with callers that still
        # pass requests_per_minute / burst.
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
    ):
        self.anonymous = anonymous or ANONYMOUS_TIER
        self.authenticated = authenticated or AUTHENTICATED_TIER
        self.premium = premium or PREMIUM_TIER
        # Legacy surface (unused internally, but avoids breaking callers)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit

    # Keep legacy attribute for any external code that reads it
    @property
    def _legacy_tier(self) -> TierConfig:
        return TierConfig("legacy", self.requests_per_window, self.window_seconds)


# ---------------------------------------------------------------------------
# Sliding-window counter (replaces the fixed-window anti-pattern)
# ---------------------------------------------------------------------------

class _SlidingWindowCounter:
    """Per-key sliding window using sub-buckets.

    Divides each window into 6 sub-intervals and keeps a running count so
    boundary bursts (the old fixed-window bug) are smoothed out.
    """

    def __init__(self, window_seconds: int = 60, sub_intervals: int = 6):
        self.window = window_seconds
        self.sub_intervals = sub_intervals
        self.sub_len = window_seconds / sub_intervals
        # key -> list of (sub_bucket_ts, count)
        self._buckets: Dict[str, List[Tuple[float, int]]] = defaultdict(list)

    def hit(self, key: str, limit: int) -> Tuple[bool, int]:
        """Record a hit.  Returns (is_limited, remaining_or_retry_after)."""
        now = time.time()
        window_start = now - self.window
        entries = self._buckets[key]

        # Purge stale sub-buckets
        entries[:] = [(ts, c) for ts, c in entries if ts > window_start]

        total = sum(c for _, c in entries)

        if total >= limit:
            # Find the oldest sub-bucket that will expire
            retry_after = int(entries[0][0] + self.window - now) + 1 if entries else self.window
            return True, retry_after

        # Record this request in the current sub-bucket
        bucket_ts = now - (now % self.sub_len)
        if entries and entries[-1][0] == bucket_ts:
            entries[-1] = (bucket_ts, entries[-1][1] + 1)
        else:
            entries.append((bucket_ts, 1))

        remaining = limit - total - 1
        return False, max(remaining, 0)


# ---------------------------------------------------------------------------
# Tier resolution helpers
# ---------------------------------------------------------------------------

# JWT secret — optional; if unset we simply can't verify tokens.
_JWT_SECRET = os.environ.get("JWT_SECRET", "")
_JWT_ALGORITHM = "HS256"


def _extract_bearer_token(request: Request) -> Optional[str]:
    """Return the raw bearer token string, or None."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # Also accept X-API-Key header as an alternative auth mechanism
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key.strip()
    return None


def _resolve_tier(request: Request, config: RateLimitConfig) -> TierConfig:
    """Determine which tier a request belongs to.

    Priority:
      1. Valid JWT with role "premium" -> premium tier
      2. Valid JWT (any other role)    -> authenticated tier
      3. No / invalid token            -> anonymous tier
    """
    token = _extract_bearer_token(request)
    if not token:
        return config.anonymous

    if not _JWT_SECRET:
        # No secret configured — can't verify; treat as anonymous
        return config.anonymous

    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        # Invalid or expired — still allow through as anonymous (don't reject
        # the request here; auth middleware will handle that if the route
        # requires authentication).
        return config.anonymous

    roles = payload.get("roles", [])
    if "premium" in roles:
        return config.premium

    return config.authenticated


def _get_client_ip(request: Request) -> str:
    """Extract client IP with basic X-Forwarded-For validation.

    Only trusts the header when the request comes through a known proxy
    (configurable via TRUSTED_PROXIES env var, comma-separated CIDRs or IPs).
    Falls back to the socket-level remote address.
    """
    trusted_raw = os.environ.get("TRUSTED_PROXIES", "")
    trusted = {p.strip() for p in trusted_raw.split(",") if p.strip()} if trusted_raw else set()

    remote = request.client.host if request.client else ""

    # If we have a trusted-proxy list, only honour X-Forwarded-For when the
    # immediate peer is in that list.
    if trusted:
        if remote in trusted:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                # Take the leftmost (client) IP
                return forwarded.split(",")[0].strip()
        return remote or "unknown"

    # No trusted-proxy list configured — still prefer the direct socket IP
    # over a header the client controls.  This closes the spoofing vector.
    return remote or "unknown"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self._counters: Dict[str, _SlidingWindowCounter] = {
            "anonymous": _SlidingWindowCounter(self.config.anonymous.window_seconds),
            "authenticated": _SlidingWindowCounter(self.config.authenticated.window_seconds),
            "premium": _SlidingWindowCounter(self.config.premium.window_seconds),
        }

    async def dispatch(self, request: Request, call_next):
        # Health checks are always free
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = _get_client_ip(request)
        tier = _resolve_tier(request, self.config)
        counter = self._counters[tier.name]

        is_limited, value = counter.hit(client_ip, tier.requests_per_window)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier.name,
                    "retry_after": value,
                },
                headers={"Retry-After": str(value)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(tier.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Tier"] = tier.name
        return response


# ---------------------------------------------------------------------------
# Factory (preserves the old signature for callers that import this)
# ---------------------------------------------------------------------------

def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        anonymous=TierConfig("anonymous", 60),
        authenticated=TierConfig("authenticated", 300),
        premium=TierConfig("premium", 1000),
    )
    return RateLimitMiddleware(app=None, config=config)
