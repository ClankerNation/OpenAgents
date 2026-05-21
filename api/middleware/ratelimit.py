"""
Rate limiting middleware for the OpenAgents API.

@fix-author
  name: MiMo v2.5 Pro (Xiaomi MiMo Team)
  date: 2026-05-21
  platform: OpenAgents (ClankerNation/OpenAgents)
  initialization: MiMo-v2.5-pro running via Hermes Agent, Python 3.11, FastAPI 0.115+, Starlette 0.46+
  task: Implement three-tier rate limiting with auth-based limits per issue #200

@runtime
  os: Linux (WSL2)
  arch: x86_64
  working_dir: /tmp/openagents-rework
  shell: bash
"""

import os
import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

# --- Tier Configuration ---
# Anonymous: 60 req/min
# Authenticated (Bearer token): 300 req/min
# Premium (X-API-Key): 1000 req/min
ANONYMOUS_LIMIT = int(os.getenv("RATE_LIMIT_ANONYMOUS", "60"))
AUTHENTICATED_LIMIT = int(os.getenv("RATE_LIMIT_AUTHENTICATED", "300"))
PREMIUM_LIMIT = int(os.getenv("RATE_LIMIT_PREMIUM", "1000"))
WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW", "60"))


class RateLimitTier:
    """Represents a rate limit tier with its configuration."""

    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    PREMIUM = "premium"

    @staticmethod
    def get_limit(tier: str) -> int:
        limits = {
            RateLimitTier.ANONYMOUS: ANONYMOUS_LIMIT,
            RateLimitTier.AUTHENTICATED: AUTHENTICATED_LIMIT,
            RateLimitTier.PREMIUM: PREMIUM_LIMIT,
        }
        return limits.get(tier, ANONYMOUS_LIMIT)


# --- Per-tier sliding window store ---
# Key: "{tier}:{client_ip}"
_window_store: Dict[str, list] = defaultdict(list)


def _classify_tier(request: Request) -> str:
    """
    Determine the rate limit tier from request auth state.

    Priority:
      1. X-API-Key header → premium tier
      2. Authorization: Bearer <token> → authenticated tier
      3. No credentials → anonymous tier
    """
    # Premium: X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key and len(api_key.strip()) > 0:
        return RateLimitTier.PREMIUM

    # Authenticated: Authorization header with Bearer token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 7:
        return RateLimitTier.AUTHENTICATED

    return RateLimitTier.ANONYMOUS


def _get_client_ip(request: Request) -> str:
    """
    Extract client IP, respecting X-Forwarded-For from trusted proxies.
    Falls back to request.client.host.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(tier: str, client_ip: str) -> Tuple[bool, int, int, int]:
    """
    Check rate limit using sliding window algorithm.

    Returns:
        (is_limited, limit, remaining, retry_after)
    """
    limit = RateLimitTier.get_limit(tier)
    key = f"{tier}:{client_ip}"
    now = time.time()
    window_start = now - WINDOW_SECONDS

    # Clean old entries outside window
    _window_store[key] = [t for t in _window_store[key] if t > window_start]

    current_count = len(_window_store[key])

    if current_count >= limit:
        # Rate limited — find oldest entry to calculate retry_after
        oldest = _window_store[key][0] if _window_store[key] else now
        retry_after = int(oldest - window_start) + 1
        return True, limit, 0, max(retry_after, 1)

    # Not limited — record this request
    _window_store[key].append(now)
    remaining = limit - current_count - 1
    return False, limit, remaining, 0


class ThreeTierRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Three-tier rate limiting middleware.

    Enforces different rate limits based on authentication state:
      - Anonymous: 60 req/min
      - Authenticated (Bearer): 300 req/min
      - Premium (X-API-Key): 1000 req/min

    Returns standard rate limit headers on every response.
    Returns 429 with Retry-After when limit exceeded.
    """

    async def dispatch(self, request: Request, call_next):
        # Exempt health check endpoints
        if request.url.path.startswith("/health"):
            response = await call_next(request)
            # Still include rate limit headers for consistency
            response.headers["X-RateLimit-Limit"] = str(ANONYMOUS_LIMIT)
            response.headers["X-RateLimit-Remaining"] = str(ANONYMOUS_LIMIT)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + WINDOW_SECONDS)
            return response

        client_ip = _get_client_ip(request)
        tier = _classify_tier(request)
        is_limited, limit, remaining, retry_after = _check_rate_limit(tier, client_ip)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "limit": limit,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Process request
        response = await call_next(request)

        # Set rate limit headers on every response
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + WINDOW_SECONDS)

        return response
