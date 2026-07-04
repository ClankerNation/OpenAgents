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
        anonymous_requests_per_window: int = 60,
        authenticated_requests_per_window: int = 300,
        premium_requests_per_window: int = 1000,
        window_seconds: int = 60,
    ):
        self.anonymous_requests_per_window = anonymous_requests_per_window
        self.authenticated_requests_per_window = authenticated_requests_per_window
        self.premium_requests_per_window = premium_requests_per_window
        self.window_seconds = window_seconds


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))

__all__ = ["RateLimitMiddleware", "RateLimitConfig", "_request_counts"]


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
        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if api_key:
            return "premium"

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return "authenticated"

        return "anonymous"

    def _get_limit(self, tier: str) -> int:
        if tier == "premium":
            return self.config.premium_requests_per_window
        if tier == "authenticated":
            return self.config.authenticated_requests_per_window
        return self.config.anonymous_requests_per_window

    def _is_rate_limited(self, client_ip: str, limit: int) -> Tuple[bool, int, int]:
        global _request_counts
        count, window_start = _request_counts[client_ip]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            _request_counts[client_ip] = (1, now)
            return False, limit - 1, int(self.config.window_seconds)

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, 0, retry_after

        _request_counts[client_ip] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, int(self.config.window_seconds - (now - window_start))

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier = self._get_tier(request)
        limit = self._get_limit(tier)
        is_limited, remaining, retry_after = self._is_rate_limited(client_ip, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(retry_after)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        anonymous_requests_per_window=requests_per_minute,
        authenticated_requests_per_window=requests_per_minute,
        premium_requests_per_window=requests_per_minute,
        window_seconds=60,
    )
    return RateLimitMiddleware(app=None, config=config)
