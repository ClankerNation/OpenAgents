"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Optional, Tuple


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: Optional[int] = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
        anonymous_requests_per_window: int = 60,
        authenticated_requests_per_window: int = 300,
        premium_requests_per_window: int = 1000,
    ):
        if requests_per_window is not None:
            # Backward compatibility: legacy single-limit behavior applies to all tiers.
            anonymous_requests_per_window = requests_per_window
            authenticated_requests_per_window = requests_per_window
            premium_requests_per_window = requests_per_window

        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.anonymous_requests_per_window = anonymous_requests_per_window
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
        api_key = request.headers.get("X-API-Key")
        api_tier = request.headers.get("X-API-Tier", "")

        if api_key and (api_key.lower().startswith("premium_") or api_tier.lower() == "premium"):
            return "premium"
        if request.headers.get("Authorization") or api_key:
            return "authenticated"
        return "anonymous"

    def _limit_for_tier(self, tier: str) -> int:
        if tier == "premium":
            return self.config.premium_requests_per_window
        if tier == "authenticated":
            return self.config.authenticated_requests_per_window
        return self.config.anonymous_requests_per_window

    def _is_rate_limited(self, client_key: str, limit: int) -> Tuple[bool, int, int]:
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[client_key] = (1, now)
            return False, limit - 1, int(now + self.config.window_seconds)

        reset_at = int(window_start + self.config.window_seconds)

        if count >= limit:
            retry_after = max(1, int(self.config.window_seconds - (now - window_start)))
            return True, retry_after, reset_at

        _request_counts[client_key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, reset_at

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier = self._get_tier(request)
        limit = self._limit_for_tier(tier)
        client_key = f"{tier}:{client_ip}"
        is_limited, value, reset_at = self._is_rate_limited(client_key, limit)
        rate_limit_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Reset": str(reset_at),
        }

        if is_limited:
            headers = {
                "Retry-After": str(value),
                "X-RateLimit-Remaining": "0",
                **rate_limit_headers,
            }
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                },
                headers=headers,
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
    anonymous_requests_per_minute: Optional[int] = None,
    authenticated_requests_per_minute: Optional[int] = None,
    premium_requests_per_minute: Optional[int] = None,
) -> RateLimitMiddleware:
    use_tiered_limits = any(
        value is not None
        for value in (
            anonymous_requests_per_minute,
            authenticated_requests_per_minute,
            premium_requests_per_minute,
        )
    )

    config = RateLimitConfig(
        requests_per_window=None if use_tiered_limits else requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
        anonymous_requests_per_window=anonymous_requests_per_minute or 60,
        authenticated_requests_per_window=authenticated_requests_per_minute or 300,
        premium_requests_per_window=premium_requests_per_minute or 1000,
    )
    return RateLimitMiddleware(app=None, config=config)
