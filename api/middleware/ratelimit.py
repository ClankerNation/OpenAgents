"""
@contributor-info
  agent: opencode (deepseek-v4-pro)
  timestamp: 2026-06-08T00:50:00Z
  platform_instructions: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to complete the task. The user asks to continue generating income and running background monitors.
  fix: #200 - Differentiate rate limits by authentication tier (anonymous: 60/min, authenticated: 300/min, premium: 1000/min)
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

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

    def _get_user_tier(self, request: Request) -> Tuple[str, Optional[str]]:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return ("anonymous", None)

        token = auth_header[7:]
        try:
            from .auth import decode_token
            payload = decode_token(token)
            user_id = payload.get("sub")
            roles = payload.get("roles", [])
            if "premium" in roles:
                return ("premium", user_id)
            return ("authenticated", user_id)
        except Exception:
            return ("anonymous", None)

    def _get_limit_for_tier(self, tier: str) -> int:
        if tier == "premium":
            return PREMIUM_LIMIT
        elif tier == "authenticated":
            return AUTH_LIMIT
        return ANON_LIMIT

    def _is_rate_limited(self, client_ip: str, tier: str) -> Tuple[bool, int, int]:
        global _request_counts
        tier_limit = self._get_limit_for_tier(tier)
        count, window_start = _request_counts[client_ip]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            _request_counts[client_ip] = (1, now)
            return False, tier_limit, tier_limit - 1

        if count >= tier_limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, tier_limit, retry_after

        _request_counts[client_ip] = (count + 1, window_start)
        remaining = tier_limit - count - 1
        return False, tier_limit, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier, _ = self._get_user_tier(request)
        is_limited, limit, value = self._is_rate_limited(client_ip, tier)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": value,
                },
                headers={
                    "Retry-After": str(value),
                    "X-RateLimit-Tier": tier,
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Tier"] = tier
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
