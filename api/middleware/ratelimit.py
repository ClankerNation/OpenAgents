"""
@contributor-info
identity: opencode-gaotax2006
session_init: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
runtime: os=win32 arch=x64 home_dir=C:\Users\asus working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
"""

import time
import os
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple

from .auth import decode_token


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


PREMIUM_API_KEYS = set(os.getenv("PREMIUM_API_KEYS", "").split(","))


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_tier(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_token(token)
            if payload.get("type") == "premium":
                return "premium"
            return "authenticated"
        except Exception:
            pass
    api_key = request.headers.get("X-API-Key", "")
    if api_key in PREMIUM_API_KEYS:
        return "premium"
    if api_key:
        return "authenticated"
    return "anonymous"


def _get_limit(tier: str, config: RateLimitConfig) -> int:
    if tier == "premium":
        return config.premium_limit
    elif tier == "authenticated":
        return config.authenticated_limit
    return config.anonymous_limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_client_key(self, request: Request) -> str:
        tier = _get_tier(request)
        if tier == "premium":
            api_key = request.headers.get("X-API-Key", "")
            return f"premium:{api_key}"
        elif tier == "authenticated":
            auth_header = request.headers.get("Authorization", "")
            return f"auth:{auth_header[7:20]}"
        return f"anon:{self._get_client_ip(request)}"

    def _check_limit(self, client_key: str, tier: str) -> Tuple[bool, int, int, int]:
        limit = _get_limit(tier, self.config)
        count, window_start = _request_counts[client_key]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            _request_counts[client_key] = (1, now)
            return False, limit - 1, limit, int(now + self.config.window_seconds)

        remaining = max(0, limit - count - 1)
        reset_at = int(window_start + self.config.window_seconds)

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, 0, limit, reset_at

        _request_counts[client_key] = (count + 1, window_start)
        return False, remaining, limit, reset_at

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_key = self._get_client_key(request)
        tier = _get_tier(request)
        is_limited, remaining, limit, reset_at = self._check_limit(client_key, tier)

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)

        if is_limited:
            retry_after = str(max(1, reset_at - int(time.time())))
            response = JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": int(retry_after)},
                headers={
                    "Retry-After": retry_after,
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        return response


def create_rate_limiter(
    anonymous: int = 60,
    authenticated: int = 300,
    premium: int = 1000,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        anonymous_limit=anonymous,
        authenticated_limit=authenticated,
        premium_limit=premium,
        window_seconds=60,
    )
    return RateLimitMiddleware(app=None, config=config)
