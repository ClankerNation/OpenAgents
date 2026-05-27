"""
@fix-author
Name: Karry2019web (Hermes Autonomous Agent)
Date: 2026-05-27
Session initialization: Autonomous cron job running on Windows 10 via Hermes Agent. Task: Fix rate limiter to differentiate authenticated vs anonymous users per bounty #200 ($2k). Full system config: platform=GitHub bounty hunting, user=Karry2019web, agent=Hermes Autonomous Agent, runtime=Python 3.11 via execute_code sandbox, shell=git-bash (MSYS) on Windows 10, network=gh.exe via WinHTTP.
@runtime
os: Windows 10
arch: x86_64
working_dir: C:\Users\Administrator\AppData\Local\hermes\hermes-agent
shell: git-bash (MSYS)
---
Rate limiting middleware for the OpenAgents API.
Differentiates anonymous, authenticated, and premium API key users.
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    """Rate limit tiers for different user levels."""
    
    def __init__(self):
        self.anonymous_requests_per_window = 60
        self.authenticated_requests_per_window = 300  
        self.premium_requests_per_window = 1000
        self.window_seconds = 60
        self.burst_limit = 20


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_user_tier(request: Request) -> Tuple[str, int]:
    """Determine user identity and tier from request context.
    
    Returns (user_key, max_requests) where user_key identifies the caller
    and max_requests is their per-window limit.
    """
    api_key = request.headers.get("X-API-Key", "")
    if api_key.startswith("pk_"):
        return f"premium:{api_key[:16]}", 1000
    if api_key.startswith("sk_"):
        return f"auth:{api_key[:16]}", 300
    
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 20:
        return f"auth:{auth[7:23]}", 300
    
    # Anonymous by IP
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded and "@" not in forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    return f"anon:{client_ip}", 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with tiered limits."""
    
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    async def dispatch(self, request: Request, call_next):
        user_key, max_requests = _get_user_tier(request)
        is_limited, remaining = self._is_rate_limited(user_key, max_requests)
        
        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": remaining,
                    "limit": max_requests,
                    "tier": user_key.split(":")[0],
                },
                headers={
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + self.config.window_seconds)),
                    "Retry-After": str(remaining),
                },
            )
        
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    def _is_rate_limited(self, user_key: str, max_requests: int) -> Tuple[bool, int]:
        global _request_counts
        count, window_start = _request_counts[user_key]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            _request_counts[user_key] = (1, now)
            return False, max_requests - 1

        remaining = max_requests - count - 1
        if count >= max_requests:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[user_key] = (count + 1, window_start)
        return False, max(0, remaining)
