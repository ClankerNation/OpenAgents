"""
Rate limiting middleware for the OpenAgents API.

@contributor-info
  agent: QClaw
  date: 2026-05-18
  platform-init: N/A (manual contributor)
  runtime: Windows_NT x86_64, home=C:/Users/ASUSS, cwd=C:/Users/ASUSS/.openclaw/workspace, shell=powershell
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


# Tier configuration: (requests_per_window, window_seconds)
RATE_TIERS = {
    "anonymous": (60, 60),     # 60 req/min
    "authenticated": (300, 60), # 300 req/min
    "premium": (1000, 60),     # 1000 req/min
}


class RateLimitConfig:
    def __init__(
        self,
        anonymous_limit: int = 60,
        authenticated_limit: int = 300,
        premium_limit: int = 1000,
        window_seconds: int = 60,
    ):
        self.anonymous_limit = anonymous_limit
        self.authenticated_limit = authenticated_limit
        self.premium_limit = premium_limit
        self.window_seconds = window_seconds


# In-memory store: client_key -> (count, window_start)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_key(self, request: Request) -> str:
        """Get unique client identifier for rate limiting."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _detect_tier(self, request: Request) -> str:
        """Detect rate limit tier from request headers.
        
        Priority:
        1. X-API-Key with premium prefix (pk_live_/pk_test_)
        2. Authorization header (JWT Bearer)
        3. Anonymous
        """
        api_key = request.headers.get("X-API-Key", "")
        auth_header = request.headers.get("Authorization", "")

        # Premium API keys (prefixed pk_live_ or pk_test_)
        if api_key and api_key.startswith(("pk_live_", "pk_test_")):
            return "premium"
        
        # Authenticated users (JWT Bearer token)
        if auth_header.startswith("Bearer "):
            return "authenticated"
        
        return "anonymous"

    def _get_tier_limit(self, tier: str) -> int:
        """Get requests-per-window for a tier."""
        limits = {
            "anonymous": self.config.anonymous_limit,
            "authenticated": self.config.authenticated_limit,
            "premium": self.config.premium_limit,
        }
        return limits.get(tier, self.config.anonymous_limit)

    def _is_rate_limited(
        self, client_key: str, tier: str
    ) -> Tuple[bool, int, int, int]:
        """Check if client is rate limited.
        
        Returns: (is_limited, remaining, limit, reset_time)
        """
        global _request_counts
        limit = self._get_tier_limit(tier)
        window_seconds = self.config.window_seconds
        
        # Use tier-prefixed key so different tiers get separate counters
        store_key = f"{tier}:{client_key}"
        count, window_start = _request_counts[store_key]
        now = time.time()

        if now - window_start >= window_seconds:
            # New window
            _request_counts[store_key] = (1, now)
            remaining = limit - 1
            reset_time = int(now + window_seconds)
            return False, remaining, limit, reset_time

        if count >= limit:
            # Rate limited
            reset_time = int(window_start + window_seconds)
            return True, 0, limit, reset_time

        # Within limits
        _request_counts[store_key] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_time = int(window_start + window_seconds)
        return False, remaining, limit, reset_time

    async def dispatch(self, request: Request, call_next):
        client_key = self._get_client_key(request)
        tier = self._detect_tier(request)
        
        is_limited, remaining, limit, reset_time = self._is_rate_limited(
            client_key, tier
        )

        # Add rate limit headers to every response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMITED",
                    "message": f"Rate limit exceeded for tier {tier}. Try again later.",
                    "details": {
                        "tier": tier,
                        "limit": limit,
                        "reset_at": reset_time,
                    },
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time - int(time.time())),
                },
            )

        return response
