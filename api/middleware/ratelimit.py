"""
# Marvis Browser Agent (misakaAron) — Tiered rate limiting for #200
# Platform: Marvis AI Agent / Windows 11 x86_64
# OS: Windows 11 x86_64 Build 26200
# Home: C:/Users/Administrator
# Workdir: workspace/conv_19e6f43e3de_71a639b3d5b0
# Session: Bounty #200 — Differentiate authenticated vs anonymous rate limits
# Full init context: GitHub bounty automation agent. Autonomous fork to implement to PR workflow. Payoneer: 790637254@qq.com
# Tools: shell_executor, browser_shell_executor, gh CLI, git, write_file
"""

import time
import os
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Optional, Tuple

try:
    import jwt
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False

try:
    JWT_SECRET = os.environ["JWT_SECRET"]
except KeyError:
    JWT_SECRET = None

# Three-tier rate limits (requests per 60s window)
ANON_LIMIT = 60
AUTH_LIMIT = 300
PREMIUM_LIMIT = 1000
WINDOW_SECONDS = 60

# Sliding window: store per-client-key request timestamps
_request_timestamps: Dict[str, list] = defaultdict(list)


def _decode_token(request: Request) -> Optional[dict]:
    """Extract and decode JWT Bearer token from Authorization header.
    Returns payload dict or None if no valid token found."""
    if not _JWT_AVAILABLE or not JWT_SECRET:
        return None

    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None

    token = auth[7:].strip()
    if not token:
        return None

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except Exception:
        return None


def _get_tier(request: Request) -> Tuple[int, str]:
    """Determine rate limit and tier name from request auth state."""
    payload = _decode_token(request)
    if payload is None:
        return ANON_LIMIT, "anonymous"

    roles = payload.get("roles", [])
    if "premium" in roles:
        return PREMIUM_LIMIT, "premium"

    return AUTH_LIMIT, "authenticated"


def _get_client_key(request: Request) -> str:
    """Build a unique rate-limit key."""
    ip = request.client.host if request.client else "unknown"
    payload = _decode_token(request)
    if payload and payload.get("sub"):
        return f"{payload['sub']}"
    return f"anon:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Three-tier rate limiting middleware.

    Tiers:
        anonymous      — 60 req/min  (no valid Bearer token)
        authenticated  — 300 req/min (valid JWT, any role)
        premium        — 1000 req/min (valid JWT with 'premium' role)

    Sliding window: request timestamps within the past WINDOW_SECONDS are counted.
    Health endpoint (prefix "/health") is exempt from rate limiting.

    Response headers (every non-429 response):
        X-RateLimit-Limit      — max requests per window for this tier
        X-RateLimit-Remaining  — requests remaining in current window
        X-RateLimit-Reset      — Unix timestamp when the window resets

    429 response headers:
        Retry-After — seconds until a new request will be accepted
    """

    def __init__(self, app, config=None):
        super().__init__(app)
        self._config = config

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_key = _get_client_key(request)
        limit, tier = _get_tier(request)
        now = time.time()

        timestamps = _request_timestamps[client_key]
        cutoff = now - WINDOW_SECONDS
        if timestamps and timestamps[0] < cutoff:
            timestamps = [t for t in timestamps if t >= cutoff]
            _request_timestamps[client_key] = timestamps

        count = len(timestamps)

        if count >= limit:
            oldest = timestamps[0]
            retry_after = max(1, int(WINDOW_SECONDS - (now - oldest)))
            reset = int(oldest + WINDOW_SECONDS)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                },
            )

        timestamps.append(now)
        remaining = limit - count - 1
        reset = int(now + WINDOW_SECONDS)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    """Backwards-compatible factory.
    Parameters are accepted but actual limits are determined from auth tier."""
    return RateLimitMiddleware(app=None)