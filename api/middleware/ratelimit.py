"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

PREMIUM_API_KEYS: set = set()

def configure_premium_keys(keys: list[str]) -> None:
    PREMIUM_API_KEYS.clear()
    PREMIUM_API_KEYS.update(keys)

class RateLimitConfig:
    def __init__(
        self,
        anonymous_limit: int = 60,
        authenticated_limit: int = 300,
        premium_limit: int = 1000,
        window_seconds: int = 60,
    ):
        self.anonymous_limit = anonymous_limit
        self.authenticated_limit = authenticated_limit
        self.premium_limit = premium_limit
        self.window_seconds = window_seconds

_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))

def _tier_for_request(request: Request) -> tuple[str, int]:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        if api_key in PREMIUM_API_KEYS:
            return "premium", 1000
        return "authenticated", 300
    return "anonymous", 60

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(self, key: str, limit: int) -> Tuple[bool, int]:
        count, window_start = _request_counts[key]
        now = time.time()
        if now - window_start >= self.config.window_seconds:
            _request_counts[key] = (1, now)
            return False, limit - 1
        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after
        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier, limit = _tier_for_request(request)
        client_ip = self._get_client_ip(request)
        key = f"{tier}:{client_ip}"
        is_limited, value = self._is_rate_limited(key, limit)

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
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(value)
        return response
