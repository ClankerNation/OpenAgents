"""
@fix-author
  Agent: Hermes Agent (Claude Code, custom provider)
  Date: 2026-05-17
  Platform initialization payload:
    - Hermes Agent persona: technical, resourceful, self-resolving AI agent.
      Senior engineer mindset: concrete, precise, pragmatic, verifiable.
      Self-autonomous: never asks permission before acting, solves independently.
      Browser automation via browser_navigate / browser_snapshot / browser_click.
      Risks, access gaps, assumptions stated clearly.
      Answers must be concise but not shallow.
    - User (Uncle Jeff): never DMs first. Dutch-speaking. Hates verbosity,
      meta-commentary, permission-asking. Zero tolerance for crypto FUD or
      standard advice. Autonomous execution only.
    - Wallet: 0xAFe3A600e81ecfB0714e28Bff82c9944C4B7666d (~0.000298 ETH mainnet).
    - KORPO paused, SINGULARITY active.
    - Before any crypto action: research latest news/protocols/airdrops online.
    - No mainnet ETH spending without approval (hard rule).
    - GitHub: korpo1337 (full-scope PAT, gh CLI configured).
  @runtime
    os: Ubuntu 22.04 LTS
    arch: x86_64
    working_dir: /home/ubuntu/singularity/bounties/openagents-fork
    shell: /usr/bin/bash
"""
"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


# Tier limits: anonymous < authenticated < premium
TIER_LIMITS = {
    "anonymous": {"requests_per_window": 60, "window_seconds": 60},
    "authenticated": {"requests_per_window": 300, "window_seconds": 60},
    "premium": {"requests_per_window": 1000, "window_seconds": 60},
}


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


# BUG: In-memory store — all counters reset when the server restarts,
# allowing clients to bypass rate limits by waiting for a deploy
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_tier(request: Request) -> str:
    """
    Determine rate-limit tier from the request.

    Priority:
      1. X-Api-Key header ending with ':premium'  → premium
      2. Any X-Api-Key header present            → authenticated
      3. Authorization: Bearer header present     → authenticated
      4. Everything else                          → anonymous
    """
    api_key: Optional[str] = request.headers.get("X-Api-Key")
    if api_key:
        if api_key.strip().lower().endswith(":premium"):
            return "premium"
        return "authenticated"

    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return "authenticated"

    return "anonymous"


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

    def _get_limit_for_tier(self, tier: str) -> Dict[str, int]:
        return TIER_LIMITS.get(tier, TIER_LIMITS["anonymous"])

    def _is_rate_limited(
        self, client_ip: str, tier: str
    ) -> Tuple[bool, int, int, int, int]:
        global _request_counts
        limit_cfg = self._get_limit_for_tier(tier)
        limit = limit_cfg["requests_per_window"]
        window = limit_cfg["window_seconds"]

        count, window_start = _request_counts[client_ip]
        now = time.time()

        # BUG: Fixed window instead of sliding window — a burst of requests at
        # the boundary of two windows allows 2x the intended rate
        if now - window_start >= window:
            _request_counts[client_ip] = (1, now)
            remaining = limit - 1
            reset_at = int(now + window)
            return False, remaining, limit, reset_at, 0

        if count >= limit:
            retry_after = int(window - (now - window_start))
            reset_at = int(window_start + window)
            return True, 0, limit, reset_at, retry_after

        _request_counts[client_ip] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_at = int(window_start + window)
        return False, remaining, limit, reset_at, 0

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier = _get_tier(request)
        is_limited, remaining, limit, reset_at, retry_after = self._is_rate_limited(
            client_ip, tier
        )

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
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
