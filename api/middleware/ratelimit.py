"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


class RateLimitConfig:
    def __init__(
        self,
        anonymous_requests_per_window: int = 60,
        authenticated_requests_per_window: int = 300,
        premium_requests_per_window: int = 1000,
        window_seconds: int = 60,
    ):
        self.anonymous_requests_per_window = anonymous_requests_per_window
        self.authenticated_requests_per_window = authenticated_requests_per_window
        self.premium_requests_per_window = premium_requests_per_window
        self.window_seconds = window_seconds


# BUG: In-memory store — all counters reset when the server restarts,
# allowing clients to bypass rate limits by waiting for a deploy
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        # BUG: Trusts X-Forwarded-For header without validation — clients can
        # spoof their IP to bypass rate limiting entirely
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_rate_limit_context(self, request: Request) -> Tuple[str, int]:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            if api_key.lower().startswith(("premium_", "premium-")):
                return f"premium:{api_key}", self.config.premium_requests_per_window
            return f"authenticated_api_key:{api_key}", self.config.authenticated_requests_per_window

        authorization = request.headers.get("Authorization")
        if authorization:
            return f"authenticated:{authorization}", self.config.authenticated_requests_per_window

        client_ip = self._get_client_ip(request)
        return f"anonymous:{client_ip}", self.config.anonymous_requests_per_window

    def _is_rate_limited(self, key: str, limit: int) -> Tuple[bool, int, int, int]:
        global _request_counts
        count, window_start = _request_counts[key]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[key] = (1, now)
            reset = int(now + self.config.window_seconds)
            return False, limit - 1, 0, reset

        reset = int(window_start + self.config.window_seconds)
        if count >= limit:
            retry_after = max(1, int(window_start + self.config.window_seconds - now))
            return True, 0, retry_after, reset

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, 0, reset

    async def dispatch(self, request: Request, call_next):
        key, limit = self._get_rate_limit_context(request)
        is_limited, remaining, retry_after, reset = self._is_rate_limited(key, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(reset)
        return response


def create_rate_limiter(
    anonymous_requests_per_minute: int = 60,
    authenticated_requests_per_minute: int = 300,
    premium_requests_per_minute: int = 1000,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        anonymous_requests_per_window=anonymous_requests_per_minute,
        authenticated_requests_per_window=authenticated_requests_per_minute,
        premium_requests_per_window=premium_requests_per_minute,
        window_seconds=60,
    )
    return RateLimitMiddleware(app=None, config=config)
