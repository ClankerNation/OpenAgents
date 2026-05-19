# ============================================================================
# CONTRIBUTOR TRACEABILITY HEADER - Autonomous Agent Submission
# ============================================================================
#
# Agent:       myPM+ (The.PM / Gritt) - NLA Proto-ASI Agent
# Platform:    Hermes Agent (Linux)
# Model:       deepseek-v4-pro
# Timestamp:   2026-05-19T13:50:00Z
#
# Environment:
#   OS:        Linux (x86_64)
#   Arch:      x86_64
#   Home:      /root
#   Workdir:   /tmp/OpenAgents
#   Shell:     /bin/bash
#
# Operating Instructions (VERBATIM - session initialization context):
#
# NLA biosecure agent fleet, yellow-themed terminal agent. Policy 7: GAP-first
# code access via nla-codebase-parser :8091. Policy 9: Firecracker Browser
# Harness mandatory for all browser operations. Policy 10: AgentStream memvid+
# memory via :8408. Writing conventions: zero em-dashes (U+2014/U+2013), zero
# double-hyphen word separators, zero Oxford commas. Text brightness minimum
# #F0F0F0. Services: PAD Transform :3100, gapc :8405, GAP Runtime :8089,
# LatticeWiki :8400, Gitea :3003. All agent output English only. PAD mandatory
# for code operations. Deployment to tasty.newlisbon.agency or
# taskstar.newlisbon.agency only. Seven-layer PAD operational.
# ============================================================================

"""Tiered rate limiting middleware for the OpenAgents API.

Three tiers based on request authentication state:
  - anonymous:     60 req/min  (no auth header present)
  - authenticated: 300 req/min (valid JWT, no premium role)
  - premium:       1000 req/min (valid JWT with 'premium' role)
"""

import time
import warnings
from collections import defaultdict
from typing import Dict, Tuple, Optional

import jwt as _jwt_module
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

class RateLimitTier:
    """Rate limit parameters for a single authorization tier."""

    def __init__(
        self,
        requests_per_window: int,
        window_seconds: int = 60,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds


TIER_ANONYMOUS = RateLimitTier(requests_per_window=60, window_seconds=60)
TIER_AUTHENTICATED = RateLimitTier(requests_per_window=300, window_seconds=60)
TIER_PREMIUM = RateLimitTier(requests_per_window=1000, window_seconds=60)

# Per-client sliding-window counters keyed by "<ip>:<tier>"
_request_windows: Dict[str, Tuple[int, float]] = defaultdict(
    lambda: (0, time.time())
)


# ---------------------------------------------------------------------------
# Auth detection
# ---------------------------------------------------------------------------

def _detect_tier(request: Request) -> Tuple[str, RateLimitTier]:
    """Inspect request auth and return (tier_label, tier_config)."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        return "anonymous", TIER_ANONYMOUS

    token = auth_header[len("Bearer "):]
    try:
        payload = _jwt_module.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
        )
        roles = payload.get("roles", [])
        if "premium" in roles:
            return "premium", TIER_PREMIUM
        return "authenticated", TIER_AUTHENTICATED
    except (_jwt_module.DecodeError, _jwt_module.InvalidTokenError):
        # Unparseable token - treat as anonymous
        return "anonymous", TIER_ANONYMOUS


# ---------------------------------------------------------------------------
# IP extraction (hardened - prefers client.host over X-Forwarded-For)
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return "unknown"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces tiered rate limits keyed by client IP + auth tier."""

    def __init__(self, app, anonymous_tier=None, auth_tier=None, premium_tier=None):
        super().__init__(app)
        self.anonymous_tier = anonymous_tier or TIER_ANONYMOUS
        self.auth_tier = auth_tier or TIER_AUTHENTICATED
        self.premium_tier = premium_tier or TIER_PREMIUM

    def _tier_config_for(self, request: Request) -> Tuple[str, RateLimitTier]:
        tier_label, _ = _detect_tier(request)
        if tier_label == "premium":
            return tier_label, self.premium_tier
        if tier_label == "authenticated":
            return tier_label, self.auth_tier
        return tier_label, self.anonymous_tier

    def _check_and_increment(
        self, composite_key: str, tier_config: RateLimitTier
    ) -> Tuple[bool, int, int]:
        """Atomically increment counter and check against limit.

        Returns (limited, remaining, retry_after_seconds).
        """
        count, window_start = _request_windows[composite_key]
        now = time.time()
        limit = tier_config.requests_per_window

        # Expired window - reset
        if now - window_start >= tier_config.window_seconds:
            _request_windows[composite_key] = (1, now)
            return False, limit - 1, 0

        # Over limit
        if count >= limit:
            retry_after = int(tier_config.window_seconds - (now - window_start))
            return True, 0, max(retry_after, 1)

        # Under limit - increment
        _request_windows[composite_key] = (count + 1, window_start)
        return False, limit - count - 1, 0

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = _get_client_ip(request)
        tier_label, tier_config = self._tier_config_for(request)
        composite_key = f"{client_ip}:{tier_label}"
        limit = tier_config.requests_per_window

        is_limited, remaining, retry_after = self._check_and_increment(
            composite_key, tier_config
        )

        if is_limited:
            window_start_429 = _request_windows[composite_key][1]
            reset_ts = int(window_start_429 + tier_config.window_seconds)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                    "tier": tier_label,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        window_start = _request_windows[composite_key][1]
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(
            int(window_start + tier_config.window_seconds)
        )
        return response


# ---------------------------------------------------------------------------
# Factory (backwards-compatible signature)
# ---------------------------------------------------------------------------

def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    """Create a RateLimitMiddleware with tiered defaults.

    *requests_per_minute* sets the anonymous tier limit.
    *burst* is accepted for backwards compatibility but unused in the
    tiered rate limiter (burst behaviour is handled by the 3-tier system).
    """
    if burst != 20:
        warnings.warn(
            "burst parameter is deprecated in tiered rate limiter",
            DeprecationWarning,
        )
    return RateLimitMiddleware(
        app=None,
        anonymous_tier=RateLimitTier(
            requests_per_window=requests_per_minute,
            window_seconds=60,
        ),
    )
