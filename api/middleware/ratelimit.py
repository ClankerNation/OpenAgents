"""Rate limiting middleware with differentiated limits for JWT vs API key auth.

@fix-author
  name: Hermes Agent (dev-nana27)
  date: 2026-07-04
  pre_session_preamble: |
    You are Hermes Agent Bot, an autonomous AI agent operating a solo
    AI-venture company. Your mission is to find and execute high-value
    bounty tasks on GitHub.
  runtime:
    os: linux
    arch: x64 (WSL2 on Windows)
    working_dir: /tmp/OpenAgents
    shell: bash
"""

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
        api_key_requests_per_window: int = 500,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.api_key_requests_per_window = api_key_requests_per_window


_request_counts: Dict[str, Dict[str, Tuple[int, float]]] = defaultdict(
    lambda: {"counts": defaultdict(lambda: (0, time.time()))}
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_key(self, request: Request) -> tuple:
        """Return (client_key, is_api_key) — uses JWT sub or API key prefix for identification."""
        # Check for API key in header
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            # Use key prefix for rate limiting identity
            prefix = api_key[:12] if len(api_key) >= 12 else api_key
            return f"apikey:{prefix}", True

        # Check for JWT Bearer token
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            # Use last 8 chars of token for identity (not full token)
            token = auth[7:]
            suffix = token[-8:] if len(token) >= 8 else token
            return f"jwt:{suffix}", False

        # Fall back to IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}", False

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_key, is_api_key = self._get_client_key(request)
        limit = (
            self.config.api_key_requests_per_window
            if is_api_key
            else self.config.requests_per_window
        )

        namespace = _request_counts[client_key]
        count, window_start = namespace["counts"][client_key]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            namespace["counts"][client_key] = (1, now)
            remaining = limit - 1
        elif count >= limit:
            retry_after = int(self.config.window_seconds - (now - window_start))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                    "limit": limit,
                    "auth_method": "api_key" if is_api_key else "jwt",
                },
                headers={"Retry-After": str(retry_after)},
            )
        else:
            namespace["counts"][client_key] = (count + 1, window_start)
            remaining = limit - count - 1

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
    api_key_requests_per_minute: int = 500,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
        api_key_requests_per_window=api_key_requests_per_minute,
    )
    return RateLimitMiddleware(app=None, config=config)
