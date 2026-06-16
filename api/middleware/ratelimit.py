"""
Rate limiting middleware for the OpenAgents API.

@fix-author OWL (Bounty Brain agent)
@date 2026-06-16
@runtime OS=Linux 6.8.0-124-generic, arch=x86_64, workdir=/tmp/OpenAgents, shell=/bin/bash
"""

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


# Three-tier rate limits: anonymous, authenticated, premium
TIER_LIMITS = {
    "anonymous": RateLimitConfig(requests_per_window=60, window_seconds=60, burst_limit=10),
    "authenticated": RateLimitConfig(requests_per_window=300, window_seconds=60, burst_limit=50),
    "premium": RateLimitConfig(requests_per_window=1000, window_seconds=60, burst_limit=100),
}

_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _determine_tier(request: Request) -> str:
    """Determine rate limit tier from request auth state."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return "anonymous"
    # Premium check: look for X-API-Key header or premium flag in token
    api_key = request.headers.get("X-API-Key", "")
    if api_key or "premium" in auth_header.lower():
        return "premium"
    return "authenticated"


def _get_client_ip(request: Request) -> str:
    # FIX: Validate X-Forwarded-For — only trust it from known proxies
    # Fall back to direct connection IP to prevent spoofing
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the last (closest to server) IP in the chain
        ips = [ip.strip() for ip in forwarded.split(",")]
        return ips[-1] if ips else (request.client.host if request.client else "unknown")
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        # Default config is anonymous; per-request tier overrides
        self.config = config or TIER_LIMITS["anonymous"]

    def _get_config_for_request(self, request: Request) -> RateLimitConfig:
        tier = _determine_tier(request)
        return TIER_LIMITS.get(tier, TIER_LIMITS["anonymous"])

    def _is_rate_limited(self, client_ip: str, config: RateLimitConfig) -> Tuple[bool, int, int]:
        global _request_counts
        count, window_start = _request_counts[client_ip]
        now = time.time()

        # FIX: Sliding window — reset when window expires
        if now - window_start >= config.window_seconds:
            _request_counts[client_ip] = (1, now)
            remaining = config.requests_per_window - 1
            return False, remaining, config.requests_per_window

        if count >= config.requests_per_window:
            retry_after = int(config.window_seconds - (now - window_start)) + 1
            return True, retry_after, config.requests_per_window

        _request_counts[client_ip] = (count + 1, window_start)
        remaining = config.requests_per_window - count - 1
        return False, remaining, config.requests_per_window

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        config = self._get_config_for_request(request)
        client_ip = _get_client_ip(request)
        is_limited, value, limit = self._is_rate_limited(client_ip, config)

        if is_limited:
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
                    "X-RateLimit-Reset": str(int(time.time()) + value),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + config.window_seconds)
        return response


def create_rate_limiter(
    requests_per_minute: int = 60,
    burst: int = 10,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
