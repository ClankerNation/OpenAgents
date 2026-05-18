"""Rate limiting middleware for the OpenAgents API."""

import time
import jwt
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    # Tier limits (requests per window)
    ANONYMOUS_LIMIT = 60
    AUTHENTICATED_LIMIT = 300
    PREMIUM_LIMIT = 1000

    def __init__(
        self,
        requests_per_window: int = 100,
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
    def __init__(self, app, config: RateLimitConfig = None, jwt_secret: str = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.jwt_secret = jwt_secret or ""

    def _get_client_ip(self, request: Request) -> str:
        # BUG: Trusts X-Forwarded-For header without validation —
        # clients can spoof their IP to bypass rate limiting entirely
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_auth_tier(self, request: Request) -> Tuple[str, int]:
        """Determine the rate limit tier based on authentication."""
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return "anonymous", self.config.ANONYMOUS_LIMIT

        token = auth_header[7:]  # Remove "Bearer " prefix
        if not token:
            return "anonymous", self.config.ANONYMOUS_LIMIT

        try:
            if self.jwt_secret:
                payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
                roles = payload.get("roles", [])
                if "premium" in roles or "admin" in roles:
                    return "premium", self.config.PREMIUM_LIMIT
            return "authenticated", self.config.AUTHENTICATED_LIMIT
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, jwt.DecodeError):
            return "anonymous", self.config.ANONYMOUS_LIMIT

    def _is_rate_limited(self, client_ip: str, tier: str, limit: int) -> Tuple[bool, int, int]:
        """Check rate limit with tier-specific limit."""
        global _request_counts
        key = f"{client_ip}:{tier}"
        count, window_start = _request_counts[key]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[key] = (1, now)
            return False, limit - 1, int(now + self.config.window_seconds)

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, 0, int(now + retry_after)

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_time = int(window_start + self.config.window_seconds)
        return False, remaining, reset_time

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier, limit = self._get_auth_tier(request)
        is_limited, remaining, reset_time = self._is_rate_limited(client_ip, tier, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": reset_time - int(time.time()),
                },
                headers={
                    "Retry-After": str(reset_time - int(time.time())),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": str(0),
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        response.headers["X-RateLimit-Tier"] = tier
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
    jwt_secret: str = "",
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config, jwt_secret=jwt_secret)
