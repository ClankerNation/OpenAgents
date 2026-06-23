"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


class RateLimitConfig:
    """Rate limit tiers based on authentication level."""

    # Tier 1: Anonymous — 60 req/min
    ANONYMOUS_LIMIT = 60
    # Tier 2: Authenticated — 300 req/min
    AUTHENTICATED_LIMIT = 300
    # Tier 3: Premium API key — 1000 req/min
    PREMIUM_LIMIT = 1000

    WINDOW_SECONDS = 60
    BURST_LIMIT = 20

    def __init__(
        self,
        requests_per_window: int = 60,
        window_seconds: int = 60,
        burst_limit: int = 20,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


# BUG: In-memory store — all counters reset when the server restarts,
# allowing clients to bypass rate limits by waiting for a deploy
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _detect_tier(self, request: Request) -> str:
        """Detect authentication tier from request headers.

        Returns one of: 'anonymous', 'authenticated', 'premium'.
        """
        # Check for premium API key in header or query param
        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if api_key and api_key.startswith("pk_"):
            return "premium"

        # Check for Bearer token
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer ") and len(auth_header) > 7:
            return "authenticated"

        return "anonymous"

    def _get_limit_for_tier(self, tier: str) -> int:
        """Return the rate limit for a given authentication tier."""
        if tier == "premium":
            return RateLimitConfig.PREMIUM_LIMIT
        if tier == "authenticated":
            return RateLimitConfig.AUTHENTICATED_LIMIT
        return RateLimitConfig.ANONYMOUS_LIMIT

    def _get_client_ip(self, request: Request) -> str:
        # Trust X-Forwarded-For only if behind a trusted proxy (checked via config)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(self, client_ip: str, tier: str) -> Tuple[bool, int]:
        limit = self._get_limit_for_tier(tier)
        global _request_counts
        count, window_start = _request_counts[client_ip]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            _request_counts[client_ip] = (1, now)
            return False, limit - 1

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[client_ip] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier = self._detect_tier(request)
        is_limited, value = self._is_rate_limited(client_ip, tier)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": value,
                },
                headers={"Retry-After": str(value)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(self._get_limit_for_tier(tier))
        response.headers["X-RateLimit-Tier"] = tier
        return response


def create_rate_limiter(
    requests_per_minute: int = 60,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
