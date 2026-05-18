"""
@contributor: hermes-agent
@platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
@env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
@timestamp: 2026-05-18

Rate limiting middleware for the OpenAgents API.

Three-tier system:
  - Anonymous: 60  req/min
  - Authenticated (valid JWT): 300 req/min
  - Premium (role "premium" in JWT): 1000 req/min

Uses a sliding-window algorithm and validates X-Forwarded-For
to prevent IP-spoofing bypasses.
"""

import ipaddress
import logging
import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, List, Optional, Tuple

try:
    from api.middleware.auth import decode_token
except ImportError:  # pragma: no cover – fallback for standalone testing
    def decode_token(token: str) -> dict:
        raise RuntimeError("auth module unavailable")

_logger = logging.getLogger("openagents.ratelimit")

# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------
RATE_LIMIT_TIERS = {
    "anonymous": 60,      # 60 req/min
    "authenticated": 300,  # 300 req/min
    "premium": 1000,       # 1000 req/min
}

WINDOW_SECONDS = 60  # 1-minute sliding window


# ---------------------------------------------------------------------------
# In-memory sliding-window store
# ---------------------------------------------------------------------------
# Each key maps to a list of timestamps representing individual requests.
# On every check we prune entries older than WINDOW_SECONDS, count the
# survivors, and compare against the tier allowance.
# ---------------------------------------------------------------------------
_request_log: Dict[str, List[float]] = defaultdict(list)


# ---------------------------------------------------------------------------
# X-Forwarded-For validation
# ---------------------------------------------------------------------------
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_valid_ip(ip_str: str) -> bool:
    """Return True if *ip_str* is a syntactically valid IP address."""
    ip_str = ip_str.strip()
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


def _is_private_ip(ip_str: str) -> bool:
    """Return True if *ip_str* belongs to a private / loopback range."""
    try:
        addr = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return True  # treat invalid as private → reject
    return any(addr in net for net in _PRIVATE_NETWORKS)


# ---------------------------------------------------------------------------
# Auth tier detection
# ---------------------------------------------------------------------------
def _determine_tier(request: Request) -> str:
    """Determine the rate-limit tier from the request's auth state.

    Looks for an ``Authorization: Bearer <token>`` header.  If present
    and the token decodes successfully, the caller gets at least
    ``authenticated``.  If the decoded token's ``roles`` list contains
    ``"premium"``, the caller gets ``premium``.
    """
    auth_header: Optional[str] = request.headers.get("Authorization")
    if not auth_header:
        return "anonymous"

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return "anonymous"

    token = parts[1].strip()
    try:
        payload = decode_token(token)
        roles = payload.get("roles", [])
        if "premium" in roles:
            return "premium"
        return "authenticated"
    except Exception:
        # Any token failure → treat as anonymous
        return "anonymous"


# ---------------------------------------------------------------------------
# Client IP extraction (with X-Forwarded-For validation)
# ---------------------------------------------------------------------------
def _get_client_ip(request: Request) -> str:
    """Return the client IP, safely handling ``X-Forwarded-For``.

    Previously the code blindly trusted the first entry of
    ``X-Forwarded-For``, which allowed clients to spoof their IP and
    bypass rate limits.  Now we validate each IP from right-to-left
    (rightmost = most trusted proxy) and pick the first valid public IP.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2, ...
        # Rightmost entries are added by trusted proxies; we scan
        # right-to-left and take the first *valid, non-private* IP.
        entries = [e.strip() for e in forwarded.split(",")]
        for entry in reversed(entries):
            if _is_valid_ip(entry) and not _is_private_ip(entry):
                return entry
            # If the entry is valid but private, keep scanning — we want
            # the outermost public IP.

    # Fallback to the direct connection IP
    if request.client and request.client.host:
        return request.client.host

    return "unknown"


# ---------------------------------------------------------------------------
# Sliding-window rate limiter
# ---------------------------------------------------------------------------
def _is_rate_limited(key: str, limit: int) -> Tuple[bool, int, int]:
    """Check the sliding-window counter for *key*.

    Returns ``(is_limited, remaining, reset_in_seconds)``.
    """
    global _request_log
    now = time.time()
    window_start = now - WINDOW_SECONDS

    # Prune timestamps outside the sliding window
    entries = _request_log[key]
    _request_log[key] = [ts for ts in entries if ts > window_start]

    current_count = len(_request_log[key])

    if current_count >= limit:
        # The oldest timestamp in the window determines when the window
        # will slide past it, which is when the limit resets.
        oldest = _request_log[key][0] if _request_log[key] else now
        reset_in = int(oldest + WINDOW_SECONDS - now) + 1
        reset_in = max(reset_in, 1)
        return True, 0, reset_in

    # Record this request
    _request_log[key].append(now)
    remaining = limit - current_count - 1
    reset_in = WINDOW_SECONDS
    return False, remaining, reset_in


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Three-tier, sliding-window rate-limiting middleware."""

    def __init__(self, app, tiers: Optional[Dict[str, int]] = None):
        super().__init__(app)
        self.tiers = tiers or RATE_LIMIT_TIERS

    async def dispatch(self, request: Request, call_next):
        client_ip = _get_client_ip(request)
        tier = _determine_tier(request)
        limit = self.tiers[tier]
        key = f"{tier}:{client_ip}"

        is_limited, remaining, reset_in = _is_rate_limited(key, limit)

        if is_limited:
            retry_after = reset_in
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
                    "X-RateLimit-Reset": str(reset_in),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_in)
        return response


def create_rate_limiter(
    tiers: Optional[Dict[str, int]] = None,
) -> RateLimitMiddleware:
    """Factory helper — mirrors the original public API."""
    return RateLimitMiddleware(app=None, tiers=tiers)