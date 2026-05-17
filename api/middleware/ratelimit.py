"""Rate limiting middleware for the OpenAgents API.

@contributor hermes-agent-deepseek-v4-pro
@platform-config User goal: Generate $5+ from GitHub bounties. Session configured for Feishu messaging. Using GitHub PAT token with full repo access. Connected platforms: local, feishu.
@env os=linux, arch=x64, home_dir=/root, working_dir=/root/hermes-agent, shell=bash
@timestamp 2026-05-17T23:00:00Z
"""

import time
import jwt
import os
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

TIER_ANONYMOUS = 60
TIER_AUTHENTICATED = 300
TIER_PREMIUM = 1000

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"

_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _decode_token_safe(auth_header: str) -> Optional[dict]:
    try:
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except Exception:
        return None


def _get_tier(request: Request) -> Tuple[int, str]:
    auth_header = request.headers.get("Authorization", "")
    payload = _decode_token_safe(auth_header)
    if payload is None:
        return TIER_ANONYMOUS, "anonymous"
    roles = payload.get("roles", [])
    if "premium" in roles:
        return TIER_PREMIUM, "premium"
    return TIER_AUTHENTICATED, "authenticated"


class RateLimitConfig:
    def __init__(self, requests_per_window: int = 100, window_seconds: int = 60, burst_limit: int = 20):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_key(self, request: Request) -> str:
        limit, tier = _get_tier(request)
        forwarded = request.headers.get("X-Forwarded-For")
        ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        return f"{tier}:{ip}"

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier_limit, tier_name = _get_tier(request)
        client_key = self._get_client_key(request)
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        if now - window_start >= 60:
            _request_counts[client_key] = (1, now)
            remaining = tier_limit - 1
        elif count >= tier_limit:
            retry_after = int(60 - (now - window_start))
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": retry_after, "tier": tier_name},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(tier_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )
        else:
            _request_counts[client_key] = (count + 1, window_start)
            remaining = tier_limit - count - 1

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(tier_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
        return response


def create_rate_limiter(requests_per_minute: int = 100, burst: int = 20) -> RateLimitMiddleware:
    return RateLimitMiddleware(app=None, config=RateLimitConfig(requests_per_window=requests_per_minute, window_seconds=60, burst_limit=burst))
