# @fix-author rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Rate limiting middleware for the OpenAgents API with tiered limits."""

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
    def __init__(
        self,
        window_seconds: int = 60,
    ):
        self.window_seconds = window_seconds
        self.tiers = {
            "anonymous": RateLimitTier.ANONYMOUS,
            "authenticated": RateLimitTier.AUTHENTICATED,
            "premium": RateLimitTier.PREMIUM,
        }

    def get_limit(self, tier: str) -> int:
        return self.tiers.get(tier, self.tiers["anonymous"])


# In-memory store keyed by (client_identifier, tier)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_identifier(self, request: Request) -> str:
        """Get client identifier from auth state or IP."""
        # Check for API key in header
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
        if api_key:
            return f"key:{api_key}"
        # Fallback to IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    def _get_auth_tier(self, request: Request) -> str:
        """Determine rate limit tier from request auth state."""
        api_key = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization")

        # Premium tier: specific API key prefix or header
        if api_key and api_key.startswith("prem_"):
            return "premium"

        # Authenticated tier: any valid API key or Bearer token
        if api_key or (auth_header and auth_header.startswith("Bearer ")):
            return "authenticated"

        return "anonymous"

    def _is_rate_limited(self, identifier: str, tier: str) -> Tuple[bool, int, int]:
        """Check rate limit. Returns (is_limited, remaining_or_retry, limit)."""
        global _request_counts
        key = f"{tier}:{identifier}"
        count, window_start = _request_counts[key]
        now = time.time()
        limit = self.config.get_limit(tier)

        if now - window_start >= self.config.window_seconds:
            _request_counts[key] = (1, now)
            return False, limit - 1, limit

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, max(retry_after, 1), limit

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, limit

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        identifier = self._get_client_identifier(request)
        tier = self._get_auth_tier(request)
        is_limited, value, limit = self._is_rate_limited(identifier, tier)

        if is_limited:
            reset_time = int(time.time()) + value
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMITED",
                    "message": "Rate limit exceeded",
                    "details": {"tier": tier, "limit": limit, "retry_after": value},
                },
                headers={
                    "Retry-After": str(value),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        response = await call_next(request)
        reset_time = int(time.time()) + self.config.window_seconds
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response


def create_rate_limiter() -> RateLimitMiddleware:
    config = RateLimitConfig(window_seconds=60)
    return RateLimitMiddleware(app=None, config=config)
