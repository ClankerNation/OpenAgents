"""Rate limiting middleware for the OpenAgents API.

Contributor: Codex for charlie12520.
Runtime instructions: private platform instructions are intentionally not disclosed.
Environment: Windows x64, PowerShell, C:/Users/charl/Desktop/AI STUFF/ten_buck_attempt/repos/OpenAgents.
"""

import hashlib
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.jwt_requests_per_window = requests_per_window
        self.api_key_requests_per_window = requests_per_window * 3
        self.anonymous_requests_per_window = max(1, requests_per_window // 2)


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

    def _get_client_identity(self, request: Request) -> Tuple[str, int]:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
            return f"api-key:{api_key_hash}", self.config.api_key_requests_per_window

        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            return (
                f"jwt:{self._get_client_ip(request)}",
                self.config.jwt_requests_per_window,
            )

        return (
            f"anonymous:{self._get_client_ip(request)}",
            self.config.anonymous_requests_per_window,
        )

    def _is_rate_limited(self, client_key: str, limit: int) -> Tuple[bool, int]:
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[client_key] = (1, now)
            return False, limit - 1

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[client_key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_key, limit = self._get_client_identity(request)
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
