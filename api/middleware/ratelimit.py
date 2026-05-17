"""
@fix-author
  name: Metatron
  date: 2026-05-16
  platform: Hermes Agent
  cron_job: 79683e6ae067
  session_identity: |
    Name: Metatron
    Creature: AI — the celestial scribe, greatest coder in the world
    Vibe: Serious, direct, no fluff. Speaks with authority.
  runtime:
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash
    python: 3.x

Tiered rate limiting middleware for the OpenAgents API.

Supports three tiers determined by request auth state:
  - anonymous:  60 requests per minute  (no auth headers)
  - authenticated: 300 requests per minute  (Authorization: Bearer <JWT>)
  - premium:    1000 requests per minute (X-API-Key header)

All responses include X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset headers.
Rate-limited (429) responses include a Retry-After header.
"""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

class RateLimitTier:
    """Configuration for a single rate limit tier."""

    def __init__(self, name: str, requests_per_window: int, window_seconds: int = 60):
        self.name = name
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds


# Predefined tiers matching the bounty specification
TIER_ANONYMOUS = RateLimitTier("anonymous", requests_per_window=60)
TIER_AUTHENTICATED = RateLimitTier("authenticated", requests_per_window=300)
TIER_PREMIUM = RateLimitTier("premium", requests_per_window=1000)

TIERS = {
    "anonymous": TIER_ANONYMOUS,
    "authenticated": TIER_AUTHENTICATED,
    "premium": TIER_PREMIUM,
}


# ---------------------------------------------------------------------------
# Backwards-compatible config (legacy single-tier API)
# ---------------------------------------------------------------------------

class RateLimitConfig:
    """Legacy single-tier config kept for backwards compatibility."""

    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


# ---------------------------------------------------------------------------
# In-memory counter store (keyed by client identity + tier)
# ---------------------------------------------------------------------------

_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


# ---------------------------------------------------------------------------
# Tier detection helpers
# ---------------------------------------------------------------------------

def _detect_tier(request: Request) -> RateLimitTier:
    """
    Determine the rate limit tier from the request's auth headers.

    Priority:
      1. X-API-Key header present → premium tier (1000 req/min)
      2. Authorization: Bearer header present → authenticated tier (300 req/min)
      3. Neither → anonymous tier (60 req/min)
    """
    if request.headers.get("X-API-Key"):
        return TIER_PREMIUM
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return TIER_AUTHENTICATED
    return TIER_ANONYMOUS


def _get_client_key(request: Request) -> str:
    """Build a stable client identity key from IP and tier."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    tier = _detect_tier(request)
    return f"{tier.name}:{client_ip}"


def _compute_rate_limit_reset(window_start: float, window_seconds: int) -> int:
    """Compute the Unix timestamp when the current window resets."""
    return int(window_start + window_seconds)


# ---------------------------------------------------------------------------
# Core middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces tiered rate limits per client."""

    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        # Store legacy config for backwards-compatible usage; tiers take priority
        self.legacy_config = config or RateLimitConfig()

    def _is_rate_limited(
        self, client_key: str, tier: RateLimitTier
    ) -> Tuple[bool, int, int]:
        """
        Check whether a request should be rate-limited.

        Returns:
            (is_limited, remaining_or_retry_after, reset_timestamp)
        """
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        # Window roll-over
        if now - window_start >= tier.window_seconds:
            _request_counts[client_key] = (1, now)
            remaining = tier.requests_per_window - 1
            reset_ts = _compute_rate_limit_reset(now, tier.window_seconds)
            return False, remaining, reset_ts

        # Over limit
        if count >= tier.requests_per_window:
            retry_after = int(tier.window_seconds - (now - window_start))
            reset_ts = _compute_rate_limit_reset(window_start, tier.window_seconds)
            return True, retry_after, reset_ts

        # Under limit — increment
        _request_counts[client_key] = (count + 1, window_start)
        remaining = tier.requests_per_window - count - 1
        reset_ts = _compute_rate_limit_reset(window_start, tier.window_seconds)
        return False, remaining, reset_ts

    async def dispatch(self, request: Request, call_next):
        # Health check is exempt from rate limiting
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier = _detect_tier(request)
        client_key = _get_client_key(request)
        is_limited, value, reset_ts = self._is_rate_limited(client_key, tier)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier.name,
                    "retry_after": value,
                },
                headers={
                    "Retry-After": str(value),
                    "X-RateLimit-Limit": str(tier.requests_per_window),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(tier.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response


# ---------------------------------------------------------------------------
# Backwards-compatible factory function
# ---------------------------------------------------------------------------

def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    """Legacy factory — creates a single-tier limiter."""
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
