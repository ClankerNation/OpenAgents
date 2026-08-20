"""
@contributor-info rafaio1
@timestamp 2026-08-20T00:00:00Z
@env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


class RateLimitTier:
    ANONYMOUS = 60       # 60 req/min
    AUTHENTICATED = 300  # 300 req/min
    PREMIUM = 1000       # 1000 req/min


class RateLimitConfig:
    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.tiers = {
            "anonymous": RateLimitTier.ANONYMOUS,
            "authenticated": RateLimitTier.AUTHENTICATED,
            "premium": RateLimitTier.PREMIUM,
        }


# In-memory store: key -> (count, window_start)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_key(self, request: Request) -> str:
        """Get rate limit key from X-Forwarded-For or client IP."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_tier(self, request: Request) -> Tuple[str, int]:
        """Determine rate limit tier from request auth state."""
        # Check for premium API key marker (set by auth middleware)
        auth_method = getattr(request.state, "auth_method", None)
        is_premium = getattr(request.state, "is_premium", False)
        
        if is_premium:
            return "premium", self.config.tiers["premium"]
        elif auth_method in ("jwt", "api_key"):
            return "authenticated", self.config.tiers["authenticated"]
        else:
            return "anonymous", self.config.tiers["anonymous"]

    def _check_rate_limit(self, key: str, limit: int) -> Tuple[bool, int, int]:
        """Check rate limit using sliding window. Returns (is_limited, remaining, reset)."""
        global _request_counts
        count, window_start = _request_counts[key]
        now = time.time()

        # Reset window if expired
        if now - window_start >= self.config.window_seconds:
            _request_counts[key] = (1, now)
            return False, limit - 1, int(now + self.config.window_seconds)

        if count >= limit:
            reset_time = int(window_start + self.config.window_seconds)
            retry_after = max(1, reset_time - int(now))
            return True, 0, reset_time

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_time = int(window_start + self.config.window_seconds)
        return False, remaining, reset_time

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_key = self._get_client_key(request)
        tier_name, tier_limit = self._get_tier(request)
        
        # Use tier-specific key to separate limits
        rate_key = f"{tier_name}:{client_key}"
        
        is_limited, remaining, reset_time = self._check_rate_limit(rate_key, tier_limit)

        if is_limited:
            retry_after = max(1, reset_time - int(time.time()))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier_name,
                    "limit": tier_limit,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(tier_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(tier_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response


def create_rate_limiter(window_seconds: int = 60) -> RateLimitMiddleware:
    config = RateLimitConfig(window_seconds=window_seconds)
    return RateLimitMiddleware(app=None, config=config)
