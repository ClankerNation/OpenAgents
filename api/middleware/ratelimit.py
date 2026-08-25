"""Rate limiting middleware for the OpenAgents API with auth-aware limits."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

# @fix-author rafaio1
# @date 2026-08-25T00:00:00Z
# @runtime linux x64 /tmp/openagents_issue_200 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
        authenticated_multiplier: float = 5.0,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.authenticated_multiplier = authenticated_multiplier


# Sliding window counter store
_request_counts: Dict[str, list] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_identifier(self, request: Request) -> str:
        """Get rate limit key from authenticated user or validated IP."""
        # Check for authenticated user in request state (set by auth middleware)
        user = getattr(request.state, "user", None)
        if user and user.get("id"):
            return f"user:{user['id']}"

        # Fallback to IP with X-Forwarded-For validation
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Only trust first IP if it matches known proxy ranges
            # For now, use rightmost non-private IP as client identifier
            ips = [ip.strip() for ip in forwarded.split(",")]
            for ip in reversed(ips):
                if not ip.startswith(("10.", "172.16.", "192.168.", "127.")):
                    return f"ip:{ip}"
            return f"ip:{ips[0]}"

        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def _is_rate_limited(self, identifier: str, is_authenticated: bool) -> Tuple[bool, int, int]:
        global _request_counts
        now = time.time()
        window_start = now - self.config.window_seconds

        # Apply multiplier for authenticated users
        limit = int(self.config.requests_per_window * (
            self.config.authenticated_multiplier if is_authenticated else 1.0
        ))

        # Clean old entries outside sliding window
        timestamps = _request_counts[identifier]
        _request_counts[identifier] = [t for t in timestamps if t > window_start]
        current_count = len(_request_counts[identifier])

        if current_count >= limit:
            # Calculate retry_after based on oldest entry in window
            oldest = min(_request_counts[identifier]) if _request_counts[identifier] else now
            retry_after = int(self.config.window_seconds - (now - oldest)) + 1
            return True, max(retry_after, 1), limit

        _request_counts[identifier].append(now)
        remaining = limit - current_count - 1
        return False, remaining, limit

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        identifier = self._get_client_identifier(request)
        user = getattr(request.state, "user", None)
        is_authenticated = bool(user and user.get("id"))

        is_limited, value, limit = self._is_rate_limited(identifier, is_authenticated)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": "Rate limit exceeded",
                    "retry_after": value,
                    "limit": limit,
                    "authenticated": is_authenticated,
                },
                headers={"Retry-After": str(value)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Window"] = str(self.config.window_seconds)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
    authenticated_multiplier: float = 5.0,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
        authenticated_multiplier=authenticated_multiplier,
    )
    return RateLimitMiddleware(app=None, config=config)
