"""Tiered rate limiting middleware for the OpenAgents API.

Enforces different rate limits based on authentication state:
- Anonymous: 60 requests/minute
- Authenticated: 300 requests/minute
- Premium: 1000 requests/minute
"""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

import jwt
import os

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"

TIER_ANONYMOUS = "anonymous"
TIER_AUTHENTICATED = "authenticated"
TIER_PREMIUM = "premium"

TIER_LIMITS = {
    TIER_ANONYMOUS: 60,
    TIER_AUTHENTICATED: 300,
    TIER_PREMIUM: 1000,
}

WINDOW_SECONDS = 60


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


_request_counts: Dict[str, Tuple[int, float, str]] = defaultdict(
    lambda: (0, time.time(), TIER_ANONYMOUS)
)


def _detect_tier(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return TIER_ANONYMOUS

    token = auth_header[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        roles = payload.get("roles", [])
        if "premium" in roles:
            return TIER_PREMIUM
        return TIER_AUTHENTICATED
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return TIER_ANONYMOUS


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_key(self, request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                return f"user:{payload.get('sub', 'unknown')}"
            except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
                pass

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        return f"ip:{ip}"

    def _get_limit_for_tier(self, tier: str) -> int:
        if tier == TIER_PREMIUM:
            return self.config.premium_limit
        if tier == TIER_AUTHENTICATED:
            return self.config.authenticated_limit
        return self.config.anonymous_limit

    def _check_rate_limit(self, client_key: str, tier: str) -> Tuple[bool, int, int, int]:
        """Returns (is_limited, remaining, limit, reset_timestamp)."""
        global _request_counts
        count, window_start, _ = _request_counts[client_key]
        now = time.time()
        limit = self._get_limit_for_tier(tier)

        if now - window_start >= self.config.window_seconds:
            _request_counts[client_key] = (1, now, tier)
            reset_at = int(now + self.config.window_seconds)
            return False, limit - 1, limit, reset_at

        if count >= limit:
            reset_at = int(window_start + self.config.window_seconds)
            retry_after = max(1, reset_at - int(now))
            return True, 0, limit, reset_at

        _request_counts[client_key] = (count + 1, window_start, tier)
        remaining = limit - count - 1
        reset_at = int(window_start + self.config.window_seconds)
        return False, remaining, limit, reset_at

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier = _detect_tier(request)
        client_key = self._get_client_key(request)
        is_limited, remaining, limit, reset_at = self._check_rate_limit(client_key, tier)

        if is_limited:
            retry_after = max(1, reset_at - int(time.time()))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                    "tier": tier,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response


def create_rate_limiter(
    anonymous_limit: int = 60,
    authenticated_limit: int = 300,
    premium_limit: int = 1000,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        anonymous_limit=anonymous_limit,
        authenticated_limit=authenticated_limit,
        premium_limit=premium_limit,
    )
    return RateLimitMiddleware(app=None, config=config)
