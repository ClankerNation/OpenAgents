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
        premium_requests_per_window: int = 1000,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.authenticated_requests_per_window = authenticated_requests_per_window
        self.premium_requests_per_window = premium_requests_per_window


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

    def _get_tier(self, request: Request) -> str:
        api_tier = (
            request.headers.get("X-API-Tier")
            or request.headers.get("X-API-Key-Tier")
            or ""
        ).strip().lower()
        if api_tier == "premium":
            return "premium"

        if request.headers.get("X-API-Key"):
            return "authenticated"

        authorization = request.headers.get("Authorization") or ""
        if authorization.lower().startswith("bearer "):
            return "authenticated"

        return "anonymous"

    def _get_rate_limit_key(self, request: Request, tier: str) -> str:
        if tier == "premium":
            premium_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
            if premium_key:
                return f"premium:{premium_key}"

        if tier == "authenticated":
            auth_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
            if auth_key:
                return f"auth:{auth_key}"

        return f"anon:{self._get_client_ip(request)}"

    def _get_tier_limit(self, tier: str) -> int:
        if tier == "premium":
            return self.config.premium_requests_per_window
        if tier == "authenticated":
            return self.config.authenticated_requests_per_window
        return self.config.requests_per_window

    def _is_rate_limited(self, client_key: str, limit: int) -> Tuple[bool, int, int]:
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            count = 0
            window_start = now
            _request_counts[client_key] = (0, window_start)

        reset_after = max(0, int(self.config.window_seconds - (now - window_start)))

        if count >= limit:
            return True, 0, reset_after

        _request_counts[client_key] = (count + 1, window_start)
        remaining = max(0, limit - count - 1)
        return False, remaining, reset_after

    async def dispatch(self, request: Request, call_next):
        tier = self._get_tier(request)
        limit = self._get_tier_limit(tier)

        if request.url.path.startswith("/health"):
            response = await call_next(request)
            response.headers["X-RateLimit-Remaining"] = str(limit)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Reset"] = "0"
            return response

        client_key = self._get_rate_limit_key(request, tier)
        is_limited, remaining, reset_after = self._is_rate_limited(client_key, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": reset_after,
                },
                headers={
                    "Retry-After": str(reset_after),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Reset": str(reset_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(reset_after)
        return response


def create_rate_limiter(
    requests_per_minute: int = 60,
    burst: int = 20,
    authenticated_requests_per_minute: int = 300,
    premium_requests_per_minute: int = 1000,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
        authenticated_requests_per_window=authenticated_requests_per_minute,
        premium_requests_per_window=premium_requests_per_minute,
    )
    return RateLimitMiddleware(app=None, config=config)
