"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
        authenticated_requests_per_window: int | None = 300,
        anonymous_requests_per_window: int | None = 60,
        premium_requests_per_window: int | None = 1000,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        # Backward compatible defaults: if not provided, preserve previous behavior
        self.authenticated_requests_per_window = (
            authenticated_requests_per_window
            if authenticated_requests_per_window is not None
            else requests_per_window
        )
        self.anonymous_requests_per_window = (
            anonymous_requests_per_window
            if anonymous_requests_per_window is not None
            else requests_per_window
        )
        self.premium_requests_per_window = (
            premium_requests_per_window
            if premium_requests_per_window is not None
            else self.authenticated_requests_per_window
        )

    def limit_for(self, tier: str) -> int:
        if tier == "premium":
            return self.premium_requests_per_window
        if tier == "authenticated":
            return self.authenticated_requests_per_window
        return self.anonymous_requests_per_window

    def bucket_for(self, client_ip: str, tier: str) -> str:
        return f"{tier}:{client_ip}"


# BUG: In-memory store — all counters reset when the server restarts,
# allowing clients to bypass rate limits by waiting for a deploy
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        # BUG: Trusts X-Forwarded-For header without validation — clients can
        # spoof their IP to bypass rate limiting entirely
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(self, client_ip: str, tier: str) -> Tuple[bool, int, int]:
        global _request_counts
        bucket = self.config.bucket_for(client_ip, tier)
        limit = self.config.limit_for(tier)
        count, window_start = _request_counts[bucket]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[bucket] = (1, now)
            reset_at = int(now + self.config.window_seconds)
            return False, limit - 1, reset_at

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            reset_at = int(window_start + self.config.window_seconds)
            return True, retry_after, reset_at

        _request_counts[bucket] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_at = int(window_start + self.config.window_seconds)
        return False, remaining, reset_at

    def _get_tier(self, request: Request) -> str:
        api_key = request.headers.get("X-Api-Key", "")
        if api_key.endswith(":premium"):
            return "premium"
        if request.headers.get("Authorization") or api_key:
            return "authenticated"
        return "anonymous"

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier = self._get_tier(request)
        is_limited, value, reset_at = self._is_rate_limited(client_ip, tier)
        limit = self.config.limit_for(tier)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                    "tier": tier,
                },
                headers={
                    "Retry-After": str(value),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
