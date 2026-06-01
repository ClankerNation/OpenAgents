# Contributor: Feltchy
# Platform: OpenClaw Gateway — agent=main, channel=whatsapp, model=deepseek-v4-pro
# Runtime: Linux 6.6.114.1-microsoft-standard-WSL2 (x64), node=v22.22.2, bash
# Workspace: /home/owner/.openclaw/workspace
"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

# Tiered rate limits (requests per 60s window)
ANON_LIMIT = 60
AUTH_LIMIT = 300
PREMIUM_LIMIT = 1000


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


# BUG: In-memory store — all counters reset when the server restarts,
# allowing clients to bypass rate limits by waiting for a deploy
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_auth_tier(self, request: Request) -> Tuple[int, str]:
        """Determine rate limit tier from request auth state.
        Returns (limit, tier_name)."""
        auth_header = request.headers.get("Authorization", "")

        # Check for premium API key (X-API-Premium header)
        if request.headers.get("X-API-Premium") == "true":
            return PREMIUM_LIMIT, "premium"

        # Check for authenticated (Bearer token or API key)
        if auth_header.startswith("Bearer ") or auth_header.startswith("ApiKey "):
            return AUTH_LIMIT, "authenticated"

        return ANON_LIMIT, "anonymous"

    def _is_rate_limited(self, client_key: str, limit: int) -> Tuple[bool, int, int]:
        """Check if client is rate limited. Returns (limited, retry_after_or_remaining, limit)."""
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            _request_counts[client_key] = (1, now)
            return False, limit - 1, limit

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after, limit

        _request_counts[client_key] = (count + 1, window_start)
        return False, limit - count - 1, limit

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        req_limit, tier = self._get_auth_tier(request)
        client_key = f"{client_ip}:{tier}"

        is_limited, value, limit = self._is_rate_limited(client_key, req_limit)

        if is_limited:
            window_reset = int(time.time() + self.config.window_seconds)
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
                    "X-RateLimit-Reset": str(window_reset),
                },
            )

        response = await call_next(request)
        window_reset = int(time.time() + self.config.window_seconds)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Reset"] = str(window_reset)
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
