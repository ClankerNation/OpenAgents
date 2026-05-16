"""Rate limiting middleware for the OpenAgents API.

Supports three tiers based on authentication:
- Anonymous: 60 requests/minute
- Authenticated (JWT): 300 requests/minute
- Premium (API key with premium flag): 1000 requests/minute
"""

import time
from collections import defaultdict
from enum import Enum
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional
import jwt
import os


class RateLimitTier(Enum):
    """Rate limit tiers with their request limits per minute."""

    ANONYMOUS = 60
    AUTHENTICATED = 300
    PREMIUM = 1000


class RateLimitConfig:
    def __init__(
        self,
        window_seconds: int = 60,
    ):
        self.window_seconds = window_seconds


# In-memory store for rate limit counters
# Key format: "{tier}:{identifier}" where identifier is IP or user ID
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self._jwt_secret = os.environ.get("JWT_SECRET", "")

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_auth_tier(self, request: Request) -> Tuple[RateLimitTier, str]:
        """Determine rate limit tier based on request authentication.

        Returns:
            Tuple of (tier, identifier) where identifier is user_id or IP
        """
        client_ip = self._get_client_ip(request)

        # Check for API key (premium tier)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # Premium API keys start with "pk_" prefix
            if api_key.startswith("pk_"):
                return RateLimitTier.PREMIUM, f"apikey:{api_key[:16]}"
            # Regular API keys get authenticated tier
            return RateLimitTier.AUTHENTICATED, f"apikey:{api_key[:16]}"

        # Check for JWT Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and self._jwt_secret:
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token,
                    self._jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_exp": False},  # Don't fail on expired for rate limit check
                )
                user_id = payload.get("sub", "")
                if user_id:
                    # Check for premium flag in token
                    if payload.get("premium", False):
                        return RateLimitTier.PREMIUM, f"user:{user_id}"
                    return RateLimitTier.AUTHENTICATED, f"user:{user_id}"
            except jwt.InvalidTokenError:
                pass  # Invalid token, fall through to anonymous

        # Default to anonymous tier
        return RateLimitTier.ANONYMOUS, f"ip:{client_ip}"

    def _check_rate_limit(
        self, tier: RateLimitTier, identifier: str
    ) -> Tuple[bool, int, int, int]:
        """Check if request should be rate limited.

        Returns:
            Tuple of (is_limited, remaining, limit, reset_seconds)
        """
        global _request_counts

        limit = tier.value
        key = f"{tier.name}:{identifier}"
        count, window_start = _request_counts[key]
        now = time.time()
        window_seconds = self.config.window_seconds

        # Calculate reset time
        reset_seconds = int(window_seconds - (now - window_start))
        if reset_seconds < 0:
            reset_seconds = window_seconds

        # Check if window has expired
        if now - window_start >= window_seconds:
            _request_counts[key] = (1, now)
            return False, limit - 1, limit, window_seconds

        # Check if over limit
        if count >= limit:
            return True, 0, limit, reset_seconds

        # Increment counter
        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, limit, reset_seconds

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # Determine auth tier and identifier
        tier, identifier = self._get_auth_tier(request)

        # Check rate limit
        is_limited, remaining, limit, reset_seconds = self._check_rate_limit(
            tier, identifier
        )

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier.name.lower(),
                    "limit": limit,
                    "retry_after": reset_seconds,
                },
                headers={
                    "Retry-After": str(reset_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_seconds),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to all responses
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_seconds)

        return response


def create_rate_limiter(window_seconds: int = 60) -> RateLimitMiddleware:
    """Create a rate limiter middleware with tiered limits."""
    config = RateLimitConfig(window_seconds=window_seconds)
    return RateLimitMiddleware(app=None, config=config)
