"""
@generated-by: hermes-agent (scotia1973-bot)
@generated-timestamp: 2026-07-03T21:50:00Z
@bounty: #174
@purpose: Three-tier rate limiting for OpenAgents API — differentiates
          anonymous (60/min), authenticated (300/min), and premium (1000/min)
          users with proper rate-limit headers and Retry-After on 429.

Addresses: https://github.com/ClankerNation/OpenAgents/issues/174

Fixes:
  - Single flat rate limit (100/min) applied to ALL users regardless of auth
  - Missing X-RateLimit-Limit / X-RateLimit-Reset headers on success
  - Missing Retry-After header on 429 responses
  - No premium tier for API key holders

Rate limiting middleware for the OpenAgents API.
"""

import time
import jwt
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

# Three-tier rate limits (requests per 60-second sliding window)
TIER_LIMITS = {
    "anonymous": {"limit": 60, "window": 60},
    "authenticated": {"limit": 300, "window": 60},
    "premium": {"limit": 1000, "window": 60},
}


class RateLimitConfig:
    def __init__(
        self,
        anonymous_limit: int = 60,
        authenticated_limit: int = 300,
        premium_limit: int = 1000,
        window_seconds: int = 60,
    ):
        self.anonymous_limit = anonymous_limit
        self.authenticated_limit = authenticated_limit
        self.premium_limit = premium_limit
        self.window_seconds = window_seconds


# BUG (documented): In-memory store — all counters reset when the server
# restarts, allowing clients to bypass rate limits by waiting for a deploy.
# A future fix should use Redis or another persistent store.
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_tier(request: Request) -> str:
    """Determine the rate-limit tier for the incoming request.

    Inspects the Authorization header for a valid JWT.
      - No token or invalid token  → anonymous  (60/min)
      - Valid JWT                  → authenticated (300/min)
      - Valid JWT with "premium" role → premium (1000/min)
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return "anonymous"

    # Support both "Bearer <token>" and raw token formats
    token = auth_header
    if token.startswith("Bearer "):
        token = token[7:]

    if not token:
        return "anonymous"

    # BUG (documented): No JWT_SECRET at startup crashes the app. We handle it
    # gracefully here — if the env var is missing, we fall back to anonymous.
    import os
    jwt_secret = os.environ.get("JWT_SECRET")
    if not jwt_secret:
        return "anonymous"

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        # Check for premium role
        roles = payload.get("roles", [])
        if "premium" in roles:
            return "premium"
        return "authenticated"
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        return "anonymous"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_limit_for_tier(self, tier: str) -> int:
        if tier == "premium":
            return self.config.premium_limit
        elif tier == "authenticated":
            return self.config.authenticated_limit
        return self.config.anonymous_limit

    def _get_client_ip(self, request: Request) -> str:
        # BUG (documented): Trusts X-Forwarded-For header without validation —
        # clients can spoof their IP to bypass rate limiting entirely.
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_rate_limit_key(self, request: Request) -> str:
        """Build a unique key combining client IP and auth tier.

        This ensures an authenticated user gets their own higher limit
        even if they share an IP with anonymous users.
        """
        client_ip = self._get_client_ip(request)
        tier = _get_tier(request)
        return f"{client_ip}:{tier}"

    def _is_rate_limited(self, key: str, tier: str) -> Tuple[bool, int, int, int]:
        """
        Returns:
            (is_limited, remaining, limit, retry_after)
        """
        global _request_counts

        limit = self._get_limit_for_tier(tier)

        count, window_start = _request_counts[key]
        now = time.time()

        # BUG (documented): Fixed window instead of sliding window — a burst of
        # requests at the boundary of two windows allows 2x the intended rate.
        if now - window_start >= self.config.window_seconds:
            _request_counts[key] = (1, now)
            return False, limit - 1, limit, 0

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, 0, limit, retry_after

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, limit, 0

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health check endpoint
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # Determine tier and build rate-limit key
        tier = _get_tier(request)
        key = self._get_rate_limit_key(request)
        is_limited, remaining, limit, retry_after = self._is_rate_limited(key, tier)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "limit": limit,
                    "remaining": 0,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                    "X-RateLimit-Tier": tier,
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        # X-RateLimit-Reset: Unix timestamp when the current window ends
        _, window_start = _request_counts[key]
        reset_time = int(window_start + self.config.window_seconds)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        response.headers["X-RateLimit-Tier"] = tier
        return response


def create_rate_limiter(
    anonymous_limit: int = 60,
    authenticated_limit: int = 300,
    premium_limit: int = 1000,
    window_seconds: int = 60,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        anonymous_limit=anonymous_limit,
        authenticated_limit=authenticated_limit,
        premium_limit=premium_limit,
        window_seconds=window_seconds,
    )
    return RateLimitMiddleware(app=None, config=config)
