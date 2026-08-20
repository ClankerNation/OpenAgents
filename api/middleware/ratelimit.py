// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
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
        requests_per_window: int = 60,
        window_seconds: int = 60,
        burst_limit: int = 20,
        authenticated_requests_per_window: int = 300,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.authenticated_requests_per_window = authenticated_requests_per_window


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

    def _is_rate_limited(self, client_ip: str) -> Tuple[bool, int]:
        global _request_counts
        count, window_start = _request_counts[client_ip]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[client_ip] = (1, now)
            return False, self.config.requests_per_window - 1

        if count >= self.config.requests_per_window:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[client_ip] = (count + 1, window_start)
        remaining = self.config.requests_per_window - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        # Differentiate limits based on authentication status
        is_authenticated = hasattr(request.state, "user") and request.state.user is not None
        limit = self.config.authenticated_requests_per_window if is_authenticated else self.config.requests_per_window

        is_limited, value = self._is_rate_limited(client_ip)
        # Override check with correct limit tier
        count, window_start = _request_counts[client_ip]
        now = time.time()
        if now - window_start >= self.config.window_seconds:
            _request_counts[client_ip] = (1, now)
            is_limited = False
            value = limit - 1
        elif count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            is_limited = True
            value = retry_after
        else:
            _request_counts[client_ip] = (count + 1, window_start)
            is_limited = False
            value = limit - count - 1

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
        response.headers["X-RateLimit-Limit"] = str(limit)
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
