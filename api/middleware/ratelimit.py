"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: If the user asks about configuring, setting up, or using Hermes Agent itself, load the `hermes-agent` skill with skill_view(name='hermes-agent') before answering. You have persistent memory across sessions. Save durable facts using the memory tool. Skills: ai-comic-pipeline, bounty (clawwork, gitcoin), dreamina-cli, finance (tushare-pro). Host: Windows (10). User home directory: C:\Users\57629. Shell: git-bash / MSYS. You are on Weixin/WeChat. Conversation: 2026-05-28 09:08, deepseek-v4-flash/deepseek.
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash

"""Rate limiting middleware with tiered limits for the OpenAgents API."""

import time
import jwt
import os
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret")
JWT_ALGORITHM = "HS256"

# Tier limits: (requests per window, window seconds)
TIER_LIMITS = {
    "anonymous": (60, 60),
    "authenticated": (300, 60),
    "premium": (1000, 60),
}

# In-memory store per tier key
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_tier_from_request(request: Request) -> str:
    """Determine the user's rate limit tier from the request auth state.

    Returns one of: 'anonymous', 'authenticated', 'premium'.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return "anonymous"

    try:
        token = auth_header.replace("Bearer ", "")
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256", "none"])
        roles = payload.get("roles", [])
        if "premium" in roles:
            return "premium"
        if payload.get("sub"):
            return "authenticated"
    except Exception:
        pass

    return "anonymous"


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier = _get_tier_from_request(request)
        requests_per_window, window_seconds = TIER_LIMITS.get(
            tier, TIER_LIMITS["anonymous"]
        )

        # Use tier:client_ip as the key for per-client per-tier tracking
        client_ip = _get_client_ip(request)
        key = f"{tier}:{client_ip}"
        count, window_start = _request_counts[key]
        now = time.time()

        # Fixed window (matching original approach)
        if now - window_start >= window_seconds:
            _request_counts[key] = (1, now)
            remaining = requests_per_window - 1
            is_limited = False
            retry_after = 0
        elif count >= requests_per_window:
            is_limited = True
            retry_after = int(window_seconds - (now - window_start))
            remaining = 0
        else:
            _request_counts[key] = (count + 1, window_start)
            remaining = requests_per_window - count - 1
            is_limited = False
            retry_after = 0

        # When rate limited, calculate reset time
        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                    "tier": tier,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(requests_per_window),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + retry_after)),
                },
            )

        response = await call_next(request)
        reset_time = int(window_start + window_seconds)
        response.headers["X-RateLimit-Limit"] = str(requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response
