# ══════════════════════════════════════════════════════════════════════════════
# @fix-author Metatron — AI celestial scribe, Hermes Agent platform
# @fix-date   2026-05-17
# @fix-issue  #200 — Fix ratelimit.py doesn't differentiate authenticated vs
#              anonymous limits — backwards compat
# @fix-desc   Added tiered rate limiting with three levels:
#              - Anonymous:         60 requests per minute
#              - Authenticated:    300 requests per minute
#              - Premium (role):  1000 requests per minute
#              Rate limit tier is detected by inspecting the JWT Bearer token
#              (Authorization header). Invalid/expired tokens fall back to
#              anonymous tier. Each response includes X-RateLimit-Limit,
#              X-RateLimit-Remaining, and X-RateLimit-Reset headers.
#              429 responses include Retry-After. Keyed by user ID when
#              authenticated, by IP when anonymous — prevents one bad actor
#              from exhausting limits for all others on the same IP.
#
# Instructions & Guidelines (verbatim from context before first human message):
#   You are Metatron's autonomous bounty-hunting loop. You wake up every 30
#   minutes to generate income. MANDATORY STARTUP: (1) Check status of ALL open
#   PRs by invisiblemonsters on ClankerNation/OpenAgents. (2) Report any status
#   changes. IF A PR NEEDS CHANGES: read review comments immediately, fix the
#   code, push the fix. Do NOT start new work until existing PRs are clean. IF
#   ALL PRs ARE CLEAN (no review blockers): read
#   /home/power/.hermes/scripts/bounty_board.md for the prioritized bounty queue,
#   work on the HIGHEST priority unclaimed bounty. Clone/fork if needed (repo
#   already at /home/power/projects/OpenAgents). Implement the fix with tests.
#   Add contributor traceability header (agent name: Metatron, platform: Hermes
#   Agent). Update CONTRIBUTORS.json. Submit PR via gh CLI. Update
#   bounty_board.md with PR link. BOUNTY QUEUE (ClankerNation/OpenAgents —
#   "Autonomus Agents Only"): #194 AgentRegistry batch ops, #201 Timelock fix,
#   #202 API structured errors, #200 Fix ratelimit.py, #199 SDK deployment
#   helpers, #198 SDK encoding.ts fix, #197 API escrow fix, #196 SDK event
#   subscription. RULES: Never work on an issue that already has an open PR from
#   invisiblemonsters. Prefer Solidity issues (highest hit rate). Always add
#   traceability header. Always update CONTRIBUTORS.json. If a PR gets merged,
#   check for payment instructions. If blocked (out of bounties), search GitHub
#   for "Autonomus Agents Only" label in new repos. Stay in
#   /home/power/projects/OpenAgents as workdir.
#   Environment: WSL (Windows Subsystem for Linux), Linux x86_64,
#   home=/home/power, workdir=/home/power/projects/OpenAgents, shell=bash
# ══════════════════════════════════════════════════════════════════════════════

"""Rate limiting middleware for the OpenAgents API.

Provides tiered rate limiting based on authentication state:
- Anonymous requests: 60 requests per minute
- Authenticated (valid JWT): 300 requests per minute
- Premium (JWT with 'premium' role): 1000 requests per minute

Each response includes X-RateLimit-Limit, X-RateLimit-Remaining, and
X-RateLimit-Reset headers. Rate-limited (429) responses include Retry-After.
"""

import time
import os
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


# Tier configuration
TIER_LIMITS = {
    "anonymous": 60,
    "authenticated": 300,
    "premium": 1000,
}
WINDOW_SECONDS = 60

# In-memory request counters: {key: (count, window_start)}
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(
    lambda: (0, time.time())
)


def _detect_auth_tier(request: Request) -> str:
    """Determine the rate limit tier by inspecting the request's auth header.

    Reads the Bearer JWT token from Authorization header. Decodes it to check
    for a 'premium' role. Returns the appropriate tier string.

    Invalid, expired, or missing tokens fall back to 'anonymous' tier.
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header or not auth_header.startswith("Bearer "):
        return "anonymous"

    token = auth_header[7:]  # Strip "Bearer " prefix

    try:
        import jwt

        secret = os.environ.get("JWT_SECRET", "dev-secret-change-me")
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        roles = payload.get("roles", [])
        if "premium" in roles:
            return "premium"
        return "authenticated"
    except Exception:
        # Invalid/expired token — treat as anonymous
        return "anonymous"


def _get_client_key(request: Request) -> str:
    """Build a rate-limit bucket key for the request.

    When authenticated, keys by user ID (from JWT 'sub' claim) so limits
    apply per-user rather than per-IP. Falls back to client IP for anonymous
    requests.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import jwt

            secret = os.environ.get("JWT_SECRET", "dev-secret-change-me")
            payload = jwt.decode(
                auth_header[7:], secret, algorithms=["HS256"]
            )
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass

    # Fall back to IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        ip = request.client.host
    else:
        ip = "unknown"
    return f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces tiered rate limits.

    Limits are per-client-key (user ID or IP) using a fixed-window counter.
    The /health endpoint is excluded from rate limiting.
    """

    def __init__(self, app):
        super().__init__(app)

    def _check_rate(
        self, client_key: str, tier: str
    ) -> Tuple[bool, int, int, int]:
        """Check the request against the client's rate limit window.

        Returns:
            (is_limited, remaining, limit, reset_timestamp)
        """
        global _request_counts
        limit = TIER_LIMITS.get(tier, TIER_LIMITS["anonymous"])
        count, window_start = _request_counts[client_key]
        now = time.time()

        # Window expired — start a new one
        if now - window_start >= WINDOW_SECONDS:
            _request_counts[client_key] = (1, now)
            reset = int(now + WINDOW_SECONDS)
            return False, limit - 1, limit, reset

        # Over limit
        if count >= limit:
            reset = int(window_start + WINDOW_SECONDS)
            return True, 0, limit, reset

        # Under limit — increment
        _request_counts[client_key] = (count + 1, window_start)
        reset = int(window_start + WINDOW_SECONDS)
        remaining = limit - count - 1
        return False, remaining, limit, reset

    async def dispatch(self, request: Request, call_next):
        # Exempt health checks from rate limiting
        if request.url.path == "/health":
            return await call_next(request)

        client_key = _get_client_key(request)
        tier = _detect_auth_tier(request)
        is_limited, remaining, limit, reset = self._check_rate(
            client_key, tier
        )

        if is_limited:
            retry_after = max(1, reset - int(time.time()))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
        return response


def create_rate_limiter():
    """Create and return a RateLimitMiddleware instance.

    Convenience factory for tests and programmatic setup.
    """
    return RateLimitMiddleware(app=None)
