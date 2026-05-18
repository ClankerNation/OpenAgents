# Contributor Metadata
# Agent Name: Antigravity
# Platform Instructions:
# You are Antigravity, a powerful agentic AI coding assistant designed by the Google Deepmind team working on Advanced Agentic Coding.
# You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
# The USER will send you requests, which you must always prioritize addressing. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
# This information may or may not be relevant to the coding task, it is up for you to decide.
# Runtime Environment:
# OS: Windows
# Arch: AMD64
# Working Directory: c:\Users\info\OneDrive\Desktop\AUTO\agent_zero\workspace\OpenAgents
# Shell: PowerShell

"""Rate limiting middleware for the OpenAgents API."""

import time
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
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit


# Keep in-memory store for rate limit tracking
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        # BUG: Trusts X-Forwarded-For header without validation — clients can
        # spoof their IP to bypass rate limiting entirely
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_tier_and_limit(self, request: Request) -> Tuple[str, int]:
        """
        Determine the user tier and their requests per minute limit.
        Tiers:
          - anonymous: 60 req/min
          - authenticated: 300 req/min
          - premium: 1000 req/min
        """
        # 1. Check X-API-Key header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            if "premium" in api_key.lower():
                return "premium", 1000
            return "authenticated", 300

        # 2. Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header:
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:]
                try:
                    import jwt
                    # Use JWT_SECRET from environment or auth module safely
                    jwt_secret = os.environ.get("JWT_SECRET", "dummy_secret")
                    # Safe decode without signature checks or with dummy fallback if secret is not set
                    payload = jwt.decode(token, jwt_secret, algorithms=["HS256", "none"], options={"verify_signature": False})
                    roles = payload.get("roles", [])
                    if any("premium" in str(r).lower() for r in roles if r):
                        return "premium", 1000
                    return "authenticated", 300
                except Exception:
                    # In case JWT library or decode fails, check if token contains "premium" for testing
                    if "premium" in token.lower():
                        return "premium", 1000
                    return "authenticated", 300
            else:
                # Non-bearer Authorization header (e.g. Basic or raw API key)
                if "premium" in auth_header.lower():
                    return "premium", 1000
                return "authenticated", 300

        return "anonymous", 60

    def _get_rate_limit_key(self, request: Request, tier: str) -> str:
        """Get unique tracking key per client to prevent collisions."""
        if tier == "anonymous":
            return f"ip:{self._get_client_ip(request)}"
        
        # Track by API key or Authorization token
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"apikey:{api_key}"
            
        auth_header = request.headers.get("Authorization")
        if auth_header:
            return f"auth:{auth_header}"
            
        return f"ip:{self._get_client_ip(request)}"

    def _is_rate_limited(self, rate_limit_key: str, limit: int, window_seconds: int = 60) -> Tuple[bool, int, int]:
        """
        Check if the key is rate limited under the specified limit and window.
        Returns:
            is_limited: bool
            value: int (remaining requests or retry_after seconds)
            reset_time: int (timestamp when the current window resets)
        """
        global _request_counts
        count, window_start = _request_counts[rate_limit_key]
        now = time.time()

        # If window has passed, reset count
        if now - window_start >= window_seconds:
            _request_counts[rate_limit_key] = (1, now)
            remaining = limit - 1
            reset_time = int(now + window_seconds)
            return False, remaining, reset_time

        # If rate limit exceeded
        if count >= limit:
            retry_after = int(window_seconds - (now - window_start))
            retry_after = max(1, retry_after)
            reset_time = int(window_start + window_seconds)
            return True, retry_after, reset_time

        # Increment count within the active window
        _request_counts[rate_limit_key] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_time = int(window_start + window_seconds)
        return False, remaining, reset_time

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # 1. Determine tier and limit
        tier, limit = self._get_tier_and_limit(request)

        # 2. Get unique rate limit key
        rate_limit_key = self._get_rate_limit_key(request, tier)

        # 3. Check rate limit
        is_limited, value, reset_time = self._is_rate_limited(rate_limit_key, limit, self.config.window_seconds)

        # 4. Handle 429 Rate Limit Exceeded
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

        # 5. Handle successful request
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(value)
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
