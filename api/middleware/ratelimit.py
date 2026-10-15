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
        anonymous_requests_per_minute: int = 60,
        authenticated_requests_per_minute: int = 300,
        premium_requests_per_minute: int = 1000,
        window_seconds: int = 60,
    ):
        self.anonymous_requests_per_minute = anonymous_requests_per_minute
        self.authenticated_requests_per_minute = authenticated_requests_per_minute
        self.premium_requests_per_minute = premium_requests_per_minute
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

    def _get_client_type(self, request: Request) -> str:
        api_key = request.headers.get("X-API-Key")
        if api_key and api_key == "premium":
            return "premium"
        if api_key:
            return "authenticated"
        return "anonymous"

    def _is_rate_limited(self, client_ip: str, client_type: str) -> Tuple[bool, int]:
        global _request_counts
        count, window_start = _request_counts[client_ip]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[client_ip] = (1, now)
            return False, self.get_limit(client_type) - 1

        if count >= self.get_limit(client_type):
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[client_ip] = (count + 1, window_start)
        remaining = self.get_limit(client_type) - count - 1
        return False, remaining

    def get_limit(self, client_type: str) -> int:
        if client_type == "premium":
            return self.config.premium_requests_per_minute
        elif client_type == "authenticated":
            return self.config.authenticated_requests_per_minute
        return self.config.anonymous_requests_per_minute

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        client_type = self._get_client_type(request)
        is_limited, value = self._is_rate_limited(client_ip, client_type)

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
        response.headers["X-RateLimit-Limit"] = str(self.get_limit(client_type))
        return response


def create_rate_limiter(
    anonymous_requests_per_minute: int = 60,
    authenticated_requests_per_minute: int = 300,
    premium_requests_per_minute: int = 1000,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        anonymous_requests_per_minute=anonymous_requests_per_minute,
        authenticated_requests_per_minute=authenticated_requests_per_minute,
        premium_requests_per_minute=premium_requests_per_minute,
        window_seconds=60,
    )
    return RateLimitMiddleware(app=None, config=config)