"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
        authenticated_requests_per_window: int | None = None,
        anonymous_requests_per_window: int | None = None,
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

    def limit_for(self, is_authenticated: bool) -> int:
        return (
            self.authenticated_requests_per_window
            if is_authenticated
            else self.anonymous_requests_per_window
        )

    def bucket_for(self, client_ip: str, is_authenticated: bool) -> str:
        return f"auth:{client_ip}" if is_authenticated else f"anon:{client_ip}"


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

    def _is_rate_limited(self, client_ip: str, is_authenticated: bool) -> Tuple[bool, int]:
        global _request_counts
        bucket = self.config.bucket_for(client_ip, is_authenticated)
        limit = self.config.limit_for(is_authenticated)
        count, window_start = _request_counts[bucket]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[bucket] = (1, now)
            return False, limit - 1

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[bucket] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        is_authenticated = bool(request.headers.get("Authorization"))
        is_limited, value = self._is_rate_limited(client_ip, is_authenticated)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                },
                headers={"Retry-After": str(value)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(self.config.requests_per_window)
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
