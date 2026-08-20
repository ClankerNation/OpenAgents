# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow

"""Rate limiting middleware for the OpenAgents API with tiered limits."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    """Configuration for tiered rate limiting."""
    
    # Tier definitions (requests per minute)
    TIER_ANONYMOUS = 60
    TIER_AUTHENTICATED = 300
    TIER_PREMIUM = 1000
    
    def __init__(
        self,
        window_seconds: int = 60,
    ):
        self.window_seconds = window_seconds
        self.tiers = {
            "anonymous": self.TIER_ANONYMOUS,
            "authenticated": self.TIER_AUTHENTICATED,
            "premium": self.TIER_PREMIUM,
        }


# In-memory store for rate limit counters
# Key: client_identifier, Value: (count, window_start)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_client_tier(request: Request) -> str:
    """Determine client tier from request authentication state."""
    # Check for premium API key header
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
    if api_key:
        # Premium keys start with "pk_live_" or similar prefix
        if isinstance(api_key, str) and (api_key.startswith("pk_live_") or api_key.startswith("Bearer pk_live_")):
            return "premium"
        # Any valid auth token gets authenticated tier
        return "authenticated"
    return "anonymous"


def _get_client_identifier(request: Request, tier: str) -> str:
    """Get unique identifier for rate limiting based on tier."""
    if tier == "anonymous":
        # Use IP for anonymous users
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take first IP only, strip whitespace
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        return f"anon:{ip}"
    elif tier == "premium":
        # Use API key hash for premium users
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "")
        return f"premium:{hash(api_key)}"
    else:
        # Use user ID or token for authenticated users
        auth_header = request.headers.get("Authorization", "")
        return f"auth:{hash(auth_header)}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _is_rate_limited(self, identifier: str, tier: str) -> Tuple[bool, int, int]:
        """Check if client is rate limited. Returns (is_limited, retry_after, remaining)."""
        global _request_counts
        limit = self.config.tiers.get(tier, self.config.tiers["anonymous"])
        count, window_start = _request_counts[identifier]
        now = time.time()

        # Reset window if expired
        if now - window_start >= self.config.window_seconds:
            _request_counts[identifier] = (1, now)
            return False, 0, limit - 1

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start)) + 1
            return True, retry_after, 0

        _request_counts[identifier] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, 0, remaining

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier = _get_client_tier(request)
        identifier = _get_client_identifier(request, tier)
        limit = self.config.tiers.get(tier, self.config.tiers["anonymous"])
        
        is_limited, retry_after, remaining = self._is_rate_limited(identifier, tier)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMITED",
                    "message": "Rate limit exceeded",
                    "details": {
                        "tier": tier,
                        "limit": limit,
                        "retry_after": retry_after,
                    },
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + self.config.window_seconds)
        return response


def create_rate_limiter() -> RateLimitMiddleware:
    """Create rate limiter with default tiered configuration."""
    config = RateLimitConfig(window_seconds=60)
    return RateLimitMiddleware(app=None, config=config)
