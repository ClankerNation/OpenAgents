"""Rate limiting middleware for the OpenAgents API.

@contributor codex-gpt5
@platform-initialization Codex runtime bootstrap + AGENTS.md directives loaded for this session.
@runtime os=Windows, arch=x86_64, working_dir=F:/jiedan/OpenAgents-200, shell=powershell
"""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


ANONYMOUS_REQUESTS_PER_WINDOW = 60
AUTHENTICATED_REQUESTS_PER_WINDOW = 300
PREMIUM_REQUESTS_PER_WINDOW = 1000


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
        anonymous_requests_per_window: int | None = None,
        authenticated_requests_per_window: int | None = None,
        premium_requests_per_window: int | None = None,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.anonymous_requests_per_window = (
            requests_per_window
            if anonymous_requests_per_window is None
            else anonymous_requests_per_window
        )
        self.authenticated_requests_per_window = (
            requests_per_window
            if authenticated_requests_per_window is None
            else authenticated_requests_per_window
        )
        self.premium_requests_per_window = (
            requests_per_window
            if premium_requests_per_window is None
            else premium_requests_per_window
        )

        if requests_per_window == 100 and anonymous_requests_per_window is None:
            self.anonymous_requests_per_window = ANONYMOUS_REQUESTS_PER_WINDOW
        if requests_per_window == 100 and authenticated_requests_per_window is None:
            self.authenticated_requests_per_window = AUTHENTICATED_REQUESTS_PER_WINDOW
        if requests_per_window == 100 and premium_requests_per_window is None:
            self.premium_requests_per_window = PREMIUM_REQUESTS_PER_WINDOW


# BUG: In-memory store — all counters reset when the server restarts,
# allowing clients to bypass rate limits by waiting for a deploy
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

    def _get_bucket(self, request: Request) -> Tuple[str, int]:
        api_key = request.headers.get("X-API-Key", "").strip()
        if api_key:
            if api_key.lower().startswith("pk_"):
                return (
                    f"premium:api_key:{api_key[:32]}",
                    self.config.premium_requests_per_window,
                )
            return (
                f"authenticated:api_key:{api_key[:32]}",
                self.config.authenticated_requests_per_window,
            )

        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.lower().startswith("bearer ") and len(auth_header) > 7:
            token_prefix = auth_header[7:39]
            return (
                f"authenticated:bearer:{token_prefix}",
                self.config.authenticated_requests_per_window,
            )

        client_ip = self._get_client_ip(request)
        return f"anonymous:ip:{client_ip}", self.config.anonymous_requests_per_window

    def _is_rate_limited(self, bucket_key: str, limit: int) -> Tuple[bool, int, int, int]:
        global _request_counts
        count, window_start = _request_counts[bucket_key]
        now = time.time()
        reset_at = int(window_start + self.config.window_seconds)

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[bucket_key] = (1, now)
            reset_at = int(now + self.config.window_seconds)
            return False, limit - 1, self.config.window_seconds, reset_at

        retry_after = max(1, int(self.config.window_seconds - (now - window_start)))
        if count >= limit:
            return True, 0, retry_after, reset_at

        _request_counts[bucket_key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, retry_after, reset_at

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        bucket_key, limit = self._get_bucket(request)
        is_limited, remaining, retry_after, reset_at = self._is_rate_limited(bucket_key, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
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
