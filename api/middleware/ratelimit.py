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
        jwt_requests_per_window: int = 100,
        api_key_requests_per_window: int = 300,
        window_seconds: int = 60,
        burst_limit: int = 20,
    ):
        self.jwt_requests_per_window = jwt_requests_per_window
        self.api_key_requests_per_window = api_key_requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


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

    def _is_rate_limited(self, client_key: str, requests_per_window: int) -> Tuple[bool, int]:
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[client_key] = (1, now)
            return False, requests_per_window - 1

        if count >= requests_per_window:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[client_key] = (count + 1, window_start)
        remaining = requests_per_window - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        auth_header = request.headers.get("Authorization", "")
        if request.headers.get("X-API-Key"):
            auth_bucket = "api_key"
            limit = self.config.api_key_requests_per_window
        elif auth_header.lower().startswith("bearer "):
            auth_bucket = "jwt"
            limit = self.config.jwt_requests_per_window
        else:
            auth_bucket = "anon"
            limit = self.config.jwt_requests_per_window

        client_key = f"{auth_bucket}:{client_ip}"
        is_limited, value = self._is_rate_limited(client_key, limit)

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
        response.headers["X-RateLimit-Auth-Type"] = auth_bucket
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    api_key_requests_per_minute: int = 300,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        jwt_requests_per_window=requests_per_minute,
        api_key_requests_per_window=api_key_requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
