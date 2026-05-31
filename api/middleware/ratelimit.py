"""Rate limiting middleware for the OpenAgents API."""

import os
import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Optional, Set, Tuple


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 60,
        authenticated_requests_per_window: int = 300,
        premium_requests_per_window: int = 1000,
        window_seconds: int = 60,
        burst_limit: int = 20,
    ):
        self.requests_per_window = requests_per_window
        self.authenticated_requests_per_window = authenticated_requests_per_window
        self.premium_requests_per_window = premium_requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


# BUG: In-memory store — all counters reset when the server restarts,
# allowing clients to bypass rate limits by waiting for a deploy
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None, premium_api_keys: Optional[Set[str]] = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.premium_api_keys = premium_api_keys or {
            key.strip()
            for key in os.getenv("RATE_LIMIT_PREMIUM_KEYS", "").split(",")
            if key.strip()
        }

    def _get_client_ip(self, request: Request) -> str:
        # BUG: Trusts X-Forwarded-For header without validation — clients can
        # spoof their IP to bypass rate limiting entirely
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_tier_and_limit(self, request: Request) -> Tuple[str, int]:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            header_tier = request.headers.get("X-API-Key-Tier", "").lower()
            if header_tier == "premium" or api_key in self.premium_api_keys:
                return "premium", self.config.premium_requests_per_window
            return "authenticated", self.config.authenticated_requests_per_window

        auth_header = request.headers.get("Authorization")
        if auth_header:
            return "authenticated", self.config.authenticated_requests_per_window

        return "anonymous", self.config.requests_per_window

    def _get_client_identifier(self, request: Request, tier: str) -> str:
        if tier in ("authenticated", "premium"):
            api_key = request.headers.get("X-API-Key")
            if api_key:
                return f"api_key:{api_key}"

            auth_header = request.headers.get("Authorization")
            if auth_header:
                return f"auth:{auth_header}"

        return f"ip:{self._get_client_ip(request)}"

    def _is_rate_limited(self, client_key: str, limit: int) -> Tuple[bool, int, int, int]:
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[client_key] = (0, now)
            count, window_start = _request_counts[client_key]

        reset_at = int(window_start + self.config.window_seconds)

        if count >= limit:
            retry_after = max(1, int(self.config.window_seconds - (now - window_start)))
            return True, 0, retry_after, reset_at

        _request_counts[client_key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, 0, reset_at

    async def dispatch(self, request: Request, call_next):
        tier, limit = self._get_tier_and_limit(request)
        client_identifier = self._get_client_identifier(request, tier)
        client_key = f"{tier}:{client_identifier}"
        is_limited, remaining, retry_after, reset_at = self._is_rate_limited(client_key, limit)
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }

        if is_limited:
            headers["Retry-After"] = str(retry_after)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers=headers,
            )

        response = await call_next(request)
        for key, value in headers.items():
            response.headers[key] = value
        return response


def create_rate_limiter(
    requests_per_minute: int = 60,
    authenticated_requests_per_minute: int = 300,
    premium_requests_per_minute: int = 1000,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        authenticated_requests_per_window=authenticated_requests_per_minute,
        premium_requests_per_window=premium_requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
