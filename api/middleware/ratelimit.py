"""Rate limiting middleware for the OpenAgents API."""

# contributor-metadata:
# - agent_name: codex-gpt5
# - platform_initialization_text: |
#     You are Codex, a coding agent based on GPT-5. You and the user share
#     the same workspace and collaborate to achieve the user's goals.
# - runtime_environment:
#     os: windows
#     arch: x64
#     working_directory: F:\jiedan\OpenAgents-200
#     shell: powershell

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Optional, Tuple


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_limit: int = 20,
        anonymous_requests_per_window: Optional[int] = None,
        authenticated_requests_per_window: Optional[int] = None,
        premium_requests_per_window: Optional[int] = None,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        if (
            requests_per_window != 100
            and anonymous_requests_per_window is None
            and authenticated_requests_per_window is None
            and premium_requests_per_window is None
        ):
            # Backward compatibility path for old callers that only set
            # requests_per_window and expect one shared limit.
            self.anonymous_requests_per_window = requests_per_window
            self.authenticated_requests_per_window = requests_per_window
            self.premium_requests_per_window = requests_per_window
        else:
            self.anonymous_requests_per_window = anonymous_requests_per_window or 60
            self.authenticated_requests_per_window = authenticated_requests_per_window or 300
            self.premium_requests_per_window = premium_requests_per_window or 1000

    def limit_for_tier(self, tier: str) -> int:
        if tier == "premium":
            return self.premium_requests_per_window
        if tier == "authenticated":
            return self.authenticated_requests_per_window
        return self.anonymous_requests_per_window


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

    def _get_identity_bucket(self, request: Request, client_ip: str) -> str:
        api_key = request.headers.get("X-API-Key", "").strip()
        auth_header = request.headers.get("Authorization", "").strip()
        if api_key:
            return f"api_key:{api_key}"
        if auth_header:
            return f"auth:{auth_header}"
        return f"ip:{client_ip}"

    def _get_request_tier(self, request: Request) -> str:
        api_key = request.headers.get("X-API-Key", "").strip()
        auth_header = request.headers.get("Authorization", "").strip()
        if api_key.startswith("pk_"):
            return "premium"
        if api_key or auth_header:
            return "authenticated"
        return "anonymous"

    def _is_rate_limited(self, bucket: str, limit: int) -> Tuple[bool, int, int]:
        global _request_counts
        count, window_start = _request_counts[bucket]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= self.config.window_seconds:
            _request_counts[bucket] = (1, now)
            reset_at = int(now + self.config.window_seconds)
            return False, limit - 1, reset_at

        if count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            reset_at = int(window_start + self.config.window_seconds)
            return True, retry_after, reset_at

        _request_counts[bucket] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_at = int(window_start + self.config.window_seconds)
        return False, remaining, reset_at

    @staticmethod
    def _add_rate_limit_headers(response, limit: int, remaining: int, reset_at: int):
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            response = await call_next(request)
            anonymous_limit = self.config.limit_for_tier("anonymous")
            reset_at = int(time.time() + self.config.window_seconds)
            return self._add_rate_limit_headers(response, anonymous_limit, anonymous_limit, reset_at)

        tier = self._get_request_tier(request)
        client_ip = self._get_client_ip(request)
        bucket = f"{tier}:{self._get_identity_bucket(request, client_ip)}"
        limit = self.config.limit_for_tier(tier)
        is_limited, value, reset_at = self._is_rate_limited(bucket, limit)

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
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        return self._add_rate_limit_headers(response, limit, value, reset_at)


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
        anonymous_requests_per_window=requests_per_minute,
        authenticated_requests_per_window=requests_per_minute,
        premium_requests_per_window=requests_per_minute,
    )
    return RateLimitMiddleware(app=None, config=config)
