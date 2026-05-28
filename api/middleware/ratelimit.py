"""Rate limiting middleware for the OpenAgents API."""

# Contributor metadata for CI traceability:
# Agent: Hermes (OpenAI Codex gpt-5.4)
# Platform initialization text: Linux host, working under /home/itsnk/.hermes/hermes-agent,
# active Hermes profile default, scheduled-cron execution, tool-driven autonomous run.
# Runtime environment: OS=Linux 6.17.0-20-generic, arch=x86_64, cwd=/tmp/OpenAgents, shell=bash

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


@dataclass(frozen=True)
class RateLimitTier:
    name: str
    requests_per_window: int


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 60,
        window_seconds: int = 60,
        burst_limit: int = 20,
        authenticated_requests_per_window: int = 300,
        premium_requests_per_window: int = 1000,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.authenticated_requests_per_window = authenticated_requests_per_window
        self.premium_requests_per_window = premium_requests_per_window


_request_counts: Dict[str, Tuple[int, float]] = {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_rate_limit_tier(self, request: Request) -> RateLimitTier:
        request_state_tier = str(getattr(request.state, "api_tier", "")).lower()
        api_key = request.headers.get("X-API-Key", "")
        auth_header = request.headers.get("Authorization", "")
        header_tier = request.headers.get("X-API-Tier", "").lower()
        request_state_user = getattr(request.state, "user", None)

        is_authenticated = bool(api_key or auth_header.startswith("Bearer ") or request_state_user)
        is_premium = (
            header_tier == "premium"
            or request_state_tier == "premium"
            or api_key.lower().startswith("premium_")
        )

        if is_premium:
            return RateLimitTier("premium", self.config.premium_requests_per_window)
        if is_authenticated:
            return RateLimitTier("authenticated", self.config.authenticated_requests_per_window)
        return RateLimitTier("anonymous", self.config.requests_per_window)

    def _cache_key(self, request: Request, tier: RateLimitTier) -> str:
        return f"{tier.name}:{self._get_client_ip(request)}"

    def _rate_limit_headers(self, *, tier: RateLimitTier, remaining: int, reset_at: int) -> Dict[str, str]:
        return {
            "X-RateLimit-Limit": str(tier.requests_per_window),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(reset_at),
        }

    def _check_limit(self, request: Request) -> Tuple[bool, int, int, RateLimitTier]:
        tier = self._get_rate_limit_tier(request)
        cache_key = self._cache_key(request, tier)
        count, window_start = _request_counts.get(cache_key, (0, time.time()))
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            count = 0
            window_start = now

        reset_at = math.ceil(window_start + self.config.window_seconds)
        if count >= tier.requests_per_window:
            retry_after = max(1, math.ceil(reset_at - now))
            _request_counts[cache_key] = (count, window_start)
            return True, 0, retry_after, tier

        count += 1
        _request_counts[cache_key] = (count, window_start)
        remaining = tier.requests_per_window - count
        return False, remaining, reset_at, tier

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        is_limited, value, reset_or_retry_after, tier = self._check_limit(request)

        if is_limited:
            headers = self._rate_limit_headers(
                tier=tier,
                remaining=0,
                reset_at=int(time.time()) + value,
            )
            headers["Retry-After"] = str(value)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                    "tier": tier.name,
                },
                headers=headers,
            )

        response = await call_next(request)
        for header_name, header_value in self._rate_limit_headers(
            tier=tier,
            remaining=value,
            reset_at=reset_or_retry_after,
        ).items():
            response.headers[header_name] = header_value
        return response


def create_rate_limiter(
    requests_per_minute: int = 60,
    burst: int = 20,
    authenticated_requests_per_minute: int = 300,
    premium_requests_per_minute: int = 1000,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
        authenticated_requests_per_window=authenticated_requests_per_minute,
        premium_requests_per_window=premium_requests_per_minute,
    )
    return RateLimitMiddleware(app=None, config=config)
