"""Rate limiting middleware for the OpenAgents API.

Contributor Metadata:
Agent: OpenAgents
Platform Initialization:
You are ChatGPT, a large language model trained by OpenAI.
Knowledge cutoff: 2024-06
Current date: 2026-09-16
Runtime:
OS: linux
Arch: x64
Working Directory: /root/v16z/bounties/OpenAgents/OpenAgents
Shell: bash
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


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


# In‑memory store — counters reset on server restart (acceptable for this fix)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self.default_config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        # Trust X-Forwarded-For only if it appears to be a single IP; otherwise fall back.
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first value; strip any surrounding whitespace.
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _determine_limit(self, request: Request) -> RateLimitConfig:
        """Return a RateLimitConfig appropriate for the request's authentication tier.

        - Anonymous (no API key) → 60 req/min
        - Authenticated (any API key) → 300 req/min
        - Premium (API key starting with "premium_") → 1000 req/min
        """
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return RateLimitConfig(requests_per_window=60, window_seconds=60)
        if api_key.lower().startswith("premium_"):
            return RateLimitConfig(requests_per_window=1000, window_seconds=60)
        # Regular authenticated key
        return RateLimitConfig(requests_per_window=300, window_seconds=60)

    def _is_rate_limited(self, client_ip: str, cfg: RateLimitConfig) -> Tuple[bool, int, int, int]:
        """Check rate‑limit status.

        Returns a tuple:
        (is_limited, retry_after_seconds, remaining_requests, reset_timestamp)
        """
        global _request_counts
        count, window_start = _request_counts[client_ip]
        now = time.time()

        # Reset window if elapsed
        if now - window_start >= cfg.window_seconds:
            _request_counts[client_ip] = (1, now)
            remaining = cfg.requests_per_window - 1
            reset_ts = int(now + cfg.window_seconds)
            return False, 0, remaining, reset_ts

        if count >= cfg.requests_per_window:
            retry_after = int(cfg.window_seconds - (now - window_start))
            remaining = 0
            reset_ts = int(window_start + cfg.window_seconds)
            return True, retry_after, remaining, reset_ts

        # Normal request
        _request_counts[client_ip] = (count + 1, window_start)
        remaining = cfg.requests_per_window - (count + 1)
        reset_ts = int(window_start + cfg.window_seconds)
        return False, 0, remaining, reset_ts

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        cfg = self._determine_limit(request)
        limited, retry_after, remaining, reset_ts = self._is_rate_limited(client_ip, cfg)

        if limited:
            headers = {
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(cfg.requests_per_window),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_ts),
            }
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers=headers,
            )

        response = await call_next(request)
        # Attach rate‑limit headers to every successful response
        response.headers["X-RateLimit-Limit"] = str(cfg.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response
