"""Rate limiting middleware with tiered limits for authenticated vs anonymous users."""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


class RateLimitTier:
    ANONYMOUS = (60, 60)
    AUTHENTICATED = (300, 60)
    PREMIUM = (1000, 60)


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    def _get_tier(self, request: Request) -> Tuple[int, int]:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer premium_"):
            return RateLimitTier.PREMIUM
        if auth.startswith("Bearer "):
            return RateLimitTier.AUTHENTICATED
        return RateLimitTier.ANONYMOUS

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(self, client_ip: str, max_req: int, window: int) -> Tuple[bool, int]:
        global _request_counts
        count, window_start = _request_counts[client_ip]
        now = time.time()
        if now - window_start >= window:
            _request_counts[client_ip] = (1, now)
            return False, max_req - 1
        if count >= max_req:
            retry_after = int(window - (now - window_start))
            return True, retry_after
        _request_counts[client_ip] = (count + 1, window_start)
        remaining = max_req - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)
        client_ip = self._get_client_ip(request)
        max_req, window = self._get_tier(request)
        is_limited, value = self._is_rate_limited(client_ip, max_req, window)
        if is_limited:
            return JSONResponse(status_code=429, content={"error": "Rate limit exceeded", "retry_after": value}, headers={"Retry-After": str(value)})
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(max_req)
        return response
