# ==============================================================================
# CONTRIBUTOR METADATA
# ==============================================================================
# Agent Name: Antigravity
# Platform Initialization Text:
# <user_information>
# The USER's OS version is windows.
# The user has 1 active workspaces, each defined by a URI and a CorpusName. Multiple URIs potentially map to the same CorpusName. The mapping is shown as follows in the format [URI] -> [CorpusName]:
# c:\Users\info\OneDrive\Desktop\AUTO -> amanmanokamana-ship-it/Manokamana-Solar
# Code relating to the user's requests should be written in the locations listed above. Avoid writing project code files to tmp, in the .gemini dir, or directly to the Desktop and similar folders unless explicitly asked.
# App Data Directory: C:\Users\info\.gemini\antigravity
# Conversation ID: 987532be-6225-48d1-9bd2-6de3af605ba1
# </user_information>
# Runtime Environment Details:
# OS: Windows
# Arch: AMD64 or x86_64
# Working Directory: c:\Users\info\OneDrive\Desktop\AUTO\agent_zero\workspace\OpenAgents
# Shell: PowerShell
# ==============================================================================

"""Rate limiting middleware for the OpenAgents API."""

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
        anon_limit: int = None,
        auth_limit: int = None,
        premium_limit: int = None,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.anon_limit = anon_limit if anon_limit is not None else (requests_per_window if requests_per_window != 100 else 60)
        self.auth_limit = auth_limit if auth_limit is not None else 300
        self.premium_limit = premium_limit if premium_limit is not None else 1000


# In-memory store
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_request_tier_and_limit(self, request: Request) -> Tuple[str, str, int]:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                from .auth import decode_token
                payload = decode_token(token)
                user_id = payload.get("sub") or payload.get("id") or payload.get("address")
                if user_id:
                    roles = payload.get("roles", [])
                    is_premium = payload.get("premium", False) or "premium" in roles
                    if is_premium:
                        return "premium", f"premium:{user_id}", self.config.premium_limit
                    else:
                        return "authenticated", f"auth:{user_id}", self.config.auth_limit
            except Exception:
                pass
        
        client_ip = self._get_client_ip(request)
        return "anonymous", f"anon:{client_ip}", self.config.anon_limit

    def _is_rate_limited(self, key: str, limit: int = None) -> Tuple[bool, int]:
        if limit is None:
            limit = self.config.requests_per_window
            
        global _request_counts
        count, window_start = _request_counts[key]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            _request_counts[key] = (1, now)
            return False, limit - 1

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return True, retry_after

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier, key, limit = self._get_request_tier_and_limit(request)
        
        global _request_counts
        count, window_start = _request_counts[key]
        now = time.time()
        
        if now - window_start >= self.config.window_seconds:
            reset_time = int(now + self.config.window_seconds)
        else:
            reset_time = int(window_start + self.config.window_seconds)

        is_limited, value = self._is_rate_limited(key, limit)

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
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
