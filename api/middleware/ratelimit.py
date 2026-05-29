# ==============================================================================
# @contributor Antigravity
# @platform-instructions
# You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
# You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
# The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
# This information may or may not be relevant to the coding task, it is up for you to decide.
# @runtime
# - OS: macOS
# - Architecture: arm64
# - Home Directory: /Users/macminim1
# - Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
# - Shell: /bin/zsh
# ==============================================================================

"""Rate limiting middleware for the OpenAgents API."""

import time
from fastapi import Request
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


# Store mapping key -> (count, window_start)
_request_counts: Dict[str, Tuple[int, float]] = {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _check_rate_limit(self, key: str, limit: int, window_seconds: int = 60) -> Tuple[bool, int, int, int]:
        """
        Returns:
            is_limited: bool
            remaining: int
            reset_time: int (Unix timestamp of reset)
            retry_after: int (seconds to wait if limited, 0 otherwise)
        """
        global _request_counts
        now = time.time()
        
        if key not in _request_counts:
            _request_counts[key] = (1, now)
            remaining = limit - 1
            reset_time = int(now + window_seconds)
            return False, remaining, reset_time, 0
            
        count, window_start = _request_counts[key]
        reset_time = int(window_start + window_seconds)
        
        # If window has expired, reset it
        if now - window_start >= window_seconds:
            _request_counts[key] = (1, now)
            remaining = limit - 1
            reset_time = int(now + window_seconds)
            return False, remaining, reset_time, 0
            
        if count >= limit:
            retry_after = int(window_start + window_seconds - now)
            if retry_after <= 0:
                retry_after = 1
            remaining = 0
            return True, remaining, reset_time, retry_after
            
        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, reset_time, 0

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # 1. Determine client key and rate limit
        client_ip = self._get_client_ip(request)
        api_key = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization")

        limit = 60
        key = f"anon_{client_ip}"
        
        if api_key:
            if "premium" in api_key.lower():
                limit = 1000
                key = f"premium_key_{api_key}"
            else:
                limit = 300
                key = f"auth_key_{api_key}"
        elif auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                # Import decode_token locally to avoid circular dependencies during startup
                from api.middleware.auth import decode_token
                payload = decode_token(token)
                user_id = payload.get("sub", "unknown")
                if "premium" in payload.get("roles", []):
                    limit = 1000
                    key = f"premium_user_{user_id}"
                else:
                    limit = 300
                    key = f"auth_user_{user_id}"
            except Exception:
                limit = 60
                key = f"anon_{client_ip}"

        # 2. Check rate limit
        is_limited, remaining, reset_time, retry_after = self._check_rate_limit(
            key, limit, self.config.window_seconds
        )

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
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

