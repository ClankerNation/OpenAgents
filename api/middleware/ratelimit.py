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
        auth_requests_per_window: int = 200,
        anon_requests_per_window: int = 20,
        window_seconds: int = 60,
        burst_limit: int = 30,
    ):
        self.auth_requests_per_window = auth_requests_per_window
        self.anon_requests_per_window = anon_requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


_request_counts: Dict[str, Dict[str, Tuple[int, float]]] = defaultdict(lambda: {
    "auth": (0, time.time()),
    "anon": (0, time.time()),
})


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_authenticated(self, request: Request) -> bool:
        auth_header = request.headers.get("Authorization", "")
        return auth_header.startswith("Bearer ")

    def _is_rate_limited(self, client_ip: str, is_auth: bool) -> Tuple[bool, int]:
        global _request_counts
        bucket_key = "auth" if is_auth else "anon"
        count, window_start = _request_counts[client_ip][bucket_key]
        now = time.time()

        limit = self.config.auth_requests_per_window if is_auth else self.config.anon_requests_per_window

        if now - window_start >= self.config.window_seconds:
            _request_counts[client_ip][bucket_key] = (1, now)
            return False, limit - 1

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[client_ip][bucket_key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        is_auth = self._is_authenticated(request)
        is_limited, value = self._is_rate_limited(client_ip, is_auth)

        limit = self.config.auth_requests_per_window if is_auth else self.config.anon_requests_per_window

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                    "bucket": "authenticated" if is_auth else "anonymous",
                },
                headers={"Retry-After": str(value)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Bucket"] = "authenticated" if is_auth else "anonymous"
        return response


def create_rate_limiter(
    auth_requests_per_minute: int = 200,
    anon_requests_per_minute: int = 20,
    burst: int = 30,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        auth_requests_per_window=auth_requests_per_minute,
        anon_requests_per_window=anon_requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
