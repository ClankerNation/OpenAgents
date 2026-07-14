# @generated-by
# Name: elevasyncsolutions-jpg
# Timestamp: 2026-07-14T21:30:00Z
# Startup configuration: Bounty solving agent for ClankerNation OpenAgents. Fixing ratelimit.py to differentiate authenticated vs anonymous users. Runtime: darwin/arm64
"""Rate limiting middleware for the OpenAgents API."""

import time
import hashlib
import os
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
        auth_multiplier: float = 5.0,
        whitelisted_paths: set = None,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.auth_multiplier = auth_multiplier
        self.whitelisted_paths = whitelisted_paths or {"/health", "/docs", "/openapi.json"}


_request_counts: Dict[str, list] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_key(self, request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_hash = hashlib.sha256(auth_header.encode()).hexdigest()[:16]
            return f"auth:{token_hash}"
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        return f"anon:{ip}"

    def _get_window_limit(self, client_key: str) -> int:
        if client_key.startswith("auth:"):
            return int(self.config.requests_per_window * self.config.auth_multiplier)
        return self.config.requests_per_window

    def _is_rate_limited(self, client_key: str) -> Tuple[bool, int]:
        now = time.time()
        window_start = now - self.config.window_seconds
        timestamps = _request_counts[client_key]
        timestamps[:] = [t for t in timestamps if t > window_start]

        limit = self._get_window_limit(client_key)
        if len(timestamps) >= limit:
            retry_after = int(timestamps[0] + self.config.window_seconds - now)
            return True, max(retry_after, 1)

        timestamps.append(now)
        remaining = limit - len(timestamps)
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.config.whitelisted_paths:
            return await call_next(request)

        client_key = self._get_client_key(request)
        limited, retry_after = self._is_rate_limited(client_key)

        if limited:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._get_window_limit(client_key))
        count = len(_request_counts[client_key])
        response.headers["X-RateLimit-Remaining"] = str(max(0, self._get_window_limit(client_key) - count))
        return response
