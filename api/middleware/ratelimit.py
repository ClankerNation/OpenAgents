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
        authenticated_requests_per_window: int = 1000,
        authenticated_window_seconds: int = 60,
        authenticated_burst_limit: int = 200,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.authenticated_requests_per_window = authenticated_requests_per_window
        self.authenticated_window_seconds = authenticated_window_seconds
        self.authenticated_burst_limit = authenticated_burst_limit


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))
_auth_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _is_rate_limited(
    store: Dict[str, Tuple[int, float]],
    key: str,
    limit: int,
    window_seconds: int,
) -> Tuple[bool, int]:
    count, window_start = store[key]
    now = time.time()

    if now - window_start >= window_seconds:
        store[key] = (1, now)
        return False, limit - 1

    if count >= limit:
        retry_after = int(window_seconds - (now - window_start))
        return True, retry_after

    store[key] = (count + 1, window_start)
    remaining = limit - count - 1
    return False, remaining


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
        return _extract_bearer_token(request) is not None

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        if self._is_authenticated(request):
            is_limited, value = _is_rate_limited(
                _auth_request_counts,
                client_ip,
                self.config.authenticated_requests_per_window,
                self.config.authenticated_window_seconds,
            )
            limit_header = self.config.authenticated_requests_per_window
        else:
            is_limited, value = _is_rate_limited(
                _request_counts,
                client_ip,
                self.config.requests_per_window,
                self.config.window_seconds,
            )
            limit_header = self.config.requests_per_window

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
        response.headers["X-RateLimit-Limit"] = str(limit_header)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
    authenticated_requests_per_minute: int = 1000,
    authenticated_burst: int = 200,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
        authenticated_requests_per_window=authenticated_requests_per_minute,
        authenticated_window_seconds=60,
        authenticated_burst_limit=authenticated_burst,
    )
    return RateLimitMiddleware(app=None, config=config)
