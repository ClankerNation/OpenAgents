"""
Hermes Agent — AI-powered automated agent for code generation and repository management.
Platform initialization: You are the Hermes Agent bounty auto-pilot for user haisui157.
User goal: Find and deliver GitHub bounty issues for payment. Operates FULLY AUTONOMOUSLY — find, build/deliver, and submit work.
User location: Brunei. Preferred payment: USDT (TRC20). Also accepts crypto (BTC, ETH, SOL, LTC, BNB, TRX), Ko-fi, and WeChat Pay.
DO NOT accept: PayPal, Stripe, Wise (unavailable in Brunei).
Runtime: OS=linux, arch=x64, working_dir=/tmp/OpenAgents, shell=bash.

3-tier rate limiting middleware for the OpenAgents API.

Tiers:
  - Anonymous (no auth):        60 req/min
  - Authenticated (JWT token):  300 req/min
  - Premium (API key):          1000 req/min

Features:
  - Sliding window counters (fixes the fixed-window burst bug)
  - X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset headers
  - 429 response with Retry-After header
  - Premium API key lookup via X-API-Key header or premium role in JWT
  - Backwards compatible: existing auth flows unchanged
"""

import time
import os
import jwt
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional
from enum import Enum


class RateLimitTier(Enum):
    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    PREMIUM = "premium"


# Tier limits (requests per 60-second sliding window)
TIER_LIMITS: Dict[RateLimitTier, int] = {
    RateLimitTier.ANONYMOUS: 60,
    RateLimitTier.AUTHENTICATED: 300,
    RateLimitTier.PREMIUM: 1000,
}

JWT_SECRET = os.environ.get("JWT_SECRET", "")

# Premium API keys — loaded from env or defaults for testing
# Format: comma-separated list of keys, or single key via PREMIUM_API_KEY
# e.g., PREMIUM_API_KEY=sk-premium-abc123
DEFAULT_PREMIUM_KEYS: Dict[str, RateLimitTier] = {}
_premium_key_raw = os.environ.get("PREMIUM_API_KEY", "")
if _premium_key_raw:
    for key in _premium_key_raw.split(","):
        key = key.strip()
        if key:
            DEFAULT_PREMIUM_KEYS[key] = RateLimitTier.PREMIUM


# In-memory sliding window counters: key -> [(timestamp, ...)]
# We store timestamps of each request within the current window
_window_counts: Dict[str, list] = defaultdict(list)


def _sliding_window_count(key: str, window_seconds: int) -> int:
    """Remove expired timestamps and return current count."""
    now = time.time()
    cutoff = now - window_seconds
    timestamps = _window_counts[key]
    # Prune expired entries
    valid = [ts for ts in timestamps if ts > cutoff]
    _window_counts[key] = valid
    return len(valid)


def _record_request(key: str) -> None:
    """Record a request timestamp for the sliding window."""
    _window_counts[key].append(time.time())


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config=None):
        super().__init__(app)
        # config is unused but kept for backwards compat
        pass

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _determine_tier(self, request: Request) -> RateLimitTier:
        """Determine the rate limit tier from the request's auth state."""
        # 1. Check for premium API key in X-API-Key header
        api_key = request.headers.get("X-API-Key")
        if api_key and DEFAULT_PREMIUM_KEYS.get(api_key) == RateLimitTier.PREMIUM:
            return RateLimitTier.PREMIUM

        # 2. Check for JWT Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if JWT_SECRET:
                try:
                    payload = jwt.decode(
                        token, JWT_SECRET, algorithms=["HS256"]
                    )
                    # Check for premium role in JWT payload
                    roles = payload.get("roles", [])
                    if "premium" in roles:
                        return RateLimitTier.PREMIUM
                    # Premium API key encoded as a special key in token
                    if payload.get("tier") == "premium":
                        return RateLimitTier.PREMIUM
                    return RateLimitTier.AUTHENTICATED
                except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                    # Expired/invalid tokens treated as anonymous
                    return RateLimitTier.ANONYMOUS
            else:
                # No JWT_SECRET set — trust the header presence
                return RateLimitTier.AUTHENTICATED

        # 3. No auth at all
        return RateLimitTier.ANONYMOUS

    def _get_rate_limit_key(self, request: Request, tier: RateLimitTier) -> str:
        """Generate the rate limit counter key for this request."""
        client_ip = self._get_client_ip(request)
        return f"{tier.value}:{client_ip}"

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier = self._determine_tier(request)
        limit = TIER_LIMITS[tier]
        window_seconds = 60
        key = self._get_rate_limit_key(request, tier)

        # Sliding window check
        current_count = _sliding_window_count(key, window_seconds)

        if current_count >= limit:
            # Calculate retry-after from the oldest remaining timestamp
            now = time.time()
            cutoff = now - window_seconds
            valid_timestamps = [ts for ts in _window_counts[key] if ts > cutoff]
            if valid_timestamps:
                oldest = min(valid_timestamps)
                retry_after = int(oldest + window_seconds - now)
            else:
                retry_after = window_seconds
            retry_after = max(retry_after, 1)

            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier.value,
                    "limit": limit,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                },
            )

        # Record this request
        _record_request(key)
        remaining = limit - current_count - 1

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + window_seconds))
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    return RateLimitMiddleware(app=None)
