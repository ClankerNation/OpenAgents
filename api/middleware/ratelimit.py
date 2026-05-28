"""Rate limiting middleware for the OpenAgents API.
@generated-by: giren1011-lab
@timestamp: 2026-05-28T08:30:00Z
@purpose: Fix #124 - Differentiate rate limits by authentication status
"""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    """Rate limit configuration per tier."""

    TIERS = {
        "anonymous": {"requests_per_window": 60, "window_seconds": 60, "burst_limit": 10},
        "authenticated": {"requests_per_window": 300, "window_seconds": 60, "burst_limit": 50},
        "premium": {"requests_per_window": 1000, "window_seconds": 60, "burst_limit": 200},
    }

    def __init__(self, tier: str = "anonymous"):
        config = self.TIERS.get(tier, self.TIERS["anonymous"])
        self.requests_per_window = config["requests_per_window"]
        self.window_seconds = config["window_seconds"]
        self.burst_limit = config["burst_limit"]
        self.tier = tier


class RateLimitEntry:
    def __init__(self):
        self.timestamps: list[float] = []
        self.burst_count: int = 0


class RateLimiter:
    """In-memory rate limiter with per-tier limits."""

    def __init__(self):
        self.entries: Dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        self.premium_api_keys: set = set()

    def _get_client_key(self, request: Request) -> Tuple[str, str]:
        api_key = request.headers.get("X-API-Key", "")
        if api_key and api_key in self.premium_api_keys:
            return (f"premium:{api_key}", "premium")
        auth_header = request.headers.get("Authorization", "")
        if auth_header and auth_header.startswith("Bearer ") and len(auth_header) > 20:
            token = auth_header[7:]
            return (f"auth:{token[:16]}", "authenticated")
        forwarded = request.headers.get("X-Forwarded-For", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        return (f"anon:{client_ip}", "anonymous")

    def check(self, request: Request) -> Optional[JSONResponse]:
        client_key, tier = self._get_client_key(request)
        config = RateLimitConfig(tier)
        entry = self.entries[client_key]
        now = time.time()
        window_start = now - config.window_seconds
        entry.timestamps = [t for t in entry.timestamps if t > window_start]
        recent_burst = sum(1 for t in entry.timestamps if t > now - 1)
        if recent_burst >= config.burst_limit:
            return JSONResponse(status_code=429, content={"detail":"Too Many Requests","retry_after":1,"tier":tier,"limit":config.requests_per_window})
        if len(entry.timestamps) >= config.requests_per_window:
            retry_after = int(entry.timestamps[0] + config.window_seconds - now)
            return JSONResponse(status_code=429, content={"detail":"Rate limit exceeded","retry_after":max(retry_after,1),"tier":tier,"limit":config.requests_per_window})
        entry.timestamps.append(now)
        return None

_rate_limiter = RateLimiter()

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = _rate_limiter.check(request)
        if response:
            return response
        return await call_next(request)
