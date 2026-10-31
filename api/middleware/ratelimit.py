r"""
Contributor Metadata (required for bounty #200)
Agent: Prosperity
Platform: OpenCode
Runtime: Windows 11, x64, PowerShell
Working Directory: D:\Prosperity
Shell: PowerShell
Model: Beam Free
Timestamp: 2026-10-31T00:00:00Z
Platform Initialization Text: OpenCode AI agent, coding agent harness, tools for file editing, shell execution, web search, browser automation. Session configured for income generation. User goal: make first income for model upgrade.
"""

"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


# Tier limits (requests per minute)
ANONYMOUS_LIMIT = 60
AUTHENTICATED_LIMIT = 300
PREMIUM_LIMIT = 1000
WINDOW_SECONDS = 60


class RateLimitConfig:
    def __init__(
        self,
        anonymous_limit: int = ANONYMOUS_LIMIT,
        authenticated_limit: int = AUTHENTICATED_LIMIT,
        premium_limit: int = PREMIUM_LIMIT,
        window_seconds: int = WINDOW_SECONDS,
    ):
        self.anonymous_limit = anonymous_limit
        self.authenticated_limit = authenticated_limit
        self.premium_limit = premium_limit
        self.window_seconds = window_seconds


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_tier(self, request: Request) -> str:
        """Determine rate limit tier from request auth state."""
        auth_header = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")

        if api_key:
            if api_key.startswith("premium_"):
                return "premium"
            return "authenticated"

        if auth_header.startswith("Bearer "):
            return "authenticated"

        return "anonymous"

    def _get_limit(self, tier: str) -> int:
        if tier == "premium":
            return self.config.premium_limit
        if tier == "authenticated":
            return self.config.authenticated_limit
        return self.config.anonymous_limit

    def _is_rate_limited(self, client_key: str, limit: int) -> Tuple[bool, int, float]:
        count, window_start = _request_counts[client_key]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            _request_counts[client_key] = (1, now)
            reset_time = now + self.config.window_seconds
            return False, limit - 1, reset_time

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            reset_time = window_start + self.config.window_seconds
            return True, retry_after, reset_time

        _request_counts[client_key] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_time = window_start + self.config.window_seconds
        return False, remaining, reset_time

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier = self._get_tier(request)
        limit = self._get_limit(tier)
        client_key = f"{client_ip}:{tier}"

        is_limited, value, reset_time = self._is_rate_limited(client_key, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                },
                headers={
                    "Retry-After": str(value),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_time)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Reset"] = str(int(reset_time))
        return response


def create_rate_limiter(
    requests_per_minute: int = 60,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        anonymous_limit=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
