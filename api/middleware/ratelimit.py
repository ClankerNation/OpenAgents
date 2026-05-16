r"""
AGENT: Gemini CLI
PLATFORM: win32 | Saturday, 16 May 2026
ENVIRONMENT: win32 | x64 | C:\Users\aalok\OpenAgents | powershell
TASK: Fix ratelimit.py tier differentiation and headers (#200)
"""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    def __init__(self):
        # Tiers: (requests_per_minute, burst_limit)
        self.tiers = {
            "anonymous": (60, 10),
            "authenticated": (300, 50),
            "premium": (1000, 100)
        }
        self.window_seconds = 60


# Sliding window storage: client_id -> [timestamps]
_request_history: Dict[str, list] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_identity(self, request: Request) -> Tuple[str, str]:
        """Returns (identity_key, tier)"""
        # 1. Check for Premium API Key (Hypothetical header for this task)
        premium_key = request.headers.get("X-Premium-Key")
        if premium_key:
            return f"premium:{premium_key}", "premium"

        # 2. Check for Authenticated User (via request state or JWT)
        # In a real app, this would be populated by an earlier auth middleware
        user = getattr(request.state, "user", None)
        if user and user.get("id"):
            return f"user:{user['id']}", "authenticated"

        # 3. Fallback to IP for Anonymous
        forwarded = request.headers.get("X-Forwarded-For")
        ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        return f"anon:{ip}", "anonymous"

    def _is_rate_limited(self, identity_key: str, tier: str) -> Tuple[bool, int, int, int]:
        """Returns (is_limited, limit, remaining, retry_after_or_reset)"""
        global _request_history
        now = time.time()
        
        limit, _ = self.config.tiers[tier]
        history = _request_history[identity_key]

        # Clean up old timestamps outside the window
        history = [ts for ts in history if now - ts < self.config.window_seconds]
        _request_history[identity_key] = history

        if len(history) >= limit:
            # Reset time is when the oldest request in the current window expires
            reset_time = int(self.config.window_seconds - (now - history[0]))
            return True, limit, 0, reset_time

        history.append(now)
        remaining = limit - len(history)
        # Reset time for headers (approximate end of window)
        reset_in = self.config.window_seconds
        return False, limit, remaining, reset_in

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        identity_key, tier = self._get_client_identity(request)
        is_limited, limit, remaining, reset = self._is_rate_limited(identity_key, tier)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": reset,
                },
                headers={
                    "Retry-After": str(reset),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset)
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
        return response


def create_rate_limiter() -> RateLimitMiddleware:
    return RateLimitMiddleware(app=None)
