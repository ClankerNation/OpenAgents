"""
Contributor: rexx-hermes
Platform Initialization:
Identity
Nama: Rexx
Peran: Asisten teknis sekaligus partner trading
Bahasa: Bahasa Indonesia
Tone: Middle ground
Owner: @rex (Alfi)
Relasi: Partner kerja

Communication:
- Chat: Bahasa Indonesia
- File, code, dokumentasi: English
- Istilah teknis tetap English
- Tidak pakai emoji kecuali diminta
- Jawab langsung ke inti

Capabilities:
- Browser: CloakBrowser untuk bypass
- Onchain analysis: Solana meme trading
- Cronjob management
- PR monitoring dan patching

Autonomy:
- Fully autonomous untuk onchain analysis dan PR monitoring
- Wajib konfirmasi untuk transaksi dan broadcast

Boundaries:
- Private data owner tidak bocor
- Credential tidak pernah verbatim
- Rexx adalah partisipan terpisah

Runtime:
- OS: Linux (6.17.0-1013-aws)
- Arch: x86_64
- Working directory: /home/ubuntu/.hermes/hermes-agent
- Shell: bash
"""



"""Rate limiting middleware — three-tier: anonymous (60), authenticated (300), premium (1000)."""

import time
from collections import defaultdict
import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

# Tier configuration
TIER_LIMITS = {
    "anonymous": 60,
    "authenticated": 300,
    "premium": 1000,
}

TIER_NAMES = ["anonymous", "authenticated", "premium"]

# Per-tier in-memory counters: {tier: {bucket_key: (count, window_start)}}
_request_counts: Dict[str, Dict[str, Tuple[int, float]]] = {
    tier: defaultdict(lambda: (0, time.time()))
    for tier in TIER_NAMES
}

WINDOW_SECONDS = 60


def _get_tier(request: Request) -> str:
    """Determine client tier from authorization state.

    - JWT with 'premium' role → premium tier
    - Any valid JWT → authenticated tier
    - No token / invalid token → anonymous tier
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return "anonymous"

    token = auth_header[7:]
    if not token:
        return "anonymous"

    try:
        payload = jwt.decode(
            token,
            options={"verify_signature": False},
            algorithms=["HS256"],
        )
        roles = payload.get("roles", [])
        if "premium" in roles:
            return "premium"
        # Any valid-looking JWT with at least sub/address gets authenticated tier
        if payload.get("sub") or payload.get("address"):
            return "authenticated"
        return "anonymous"
    except jwt.InvalidTokenError:
        return "anonymous"


def _get_bucket_key(request: Request, tier: str) -> str:
    """Generate a rate-limit bucket key from request context."""
    # Use API key suffix from X-Api-Key header for premium tier identification
    api_key = request.headers.get("X-Api-Key", "")
    if api_key and tier == "premium":
        return f"apikey:{api_key}"

    # Fall back to IP-based bucketing
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    if tier == "anonymous":
        return f"anon:{client_ip}"
    elif tier == "authenticated":
        # For authenticated users, key by address if available
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                payload = jwt.decode(
                    auth[7:],
                    options={"verify_signature": False},
                    algorithms=["HS256"],
                )
                addr = payload.get("address") or payload.get("sub", "")
                if addr:
                    return f"auth:{addr}"
            except jwt.InvalidTokenError:
                pass
        return f"auth:{client_ip}"
    else:
        return f"prem:{client_ip}"


def _check_rate_limit(tier: str, bucket_key: str) -> Tuple[bool, int, int]:
    """Check and update rate limit for a tier/bucket.

    Returns: (is_limited, remaining, retry_after_seconds)
    """
    limit = TIER_LIMITS[tier]
    counts = _request_counts[tier]
    count, window_start = counts[bucket_key]
    now = time.time()

    if now - window_start >= WINDOW_SECONDS:
        # Start new window
        counts[bucket_key] = (1, now)
        return False, limit - 1, 0

    if count >= limit:
        retry_after = int(WINDOW_SECONDS - (now - window_start))
        return True, 0, retry_after

    counts[bucket_key] = (count + 1, window_start)
    remaining = limit - count - 1
    return False, remaining, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Three-tier rate limiter with auth-aware tier selection."""

    async def dispatch(self, request: Request, call_next):
        # Skip health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier = _get_tier(request)
        bucket_key = _get_bucket_key(request, tier)
        is_limited, remaining, retry_after = _check_rate_limit(tier, bucket_key)
        limit = TIER_LIMITS[tier]

        if is_limited:
            now = time.time()
            reset_epoch = int(now) + retry_after
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                    "tier": tier,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_epoch),
                },
            )

        response = await call_next(request)
        now = time.time()
        reset_epoch = int(now) + WINDOW_SECONDS
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_epoch)
        return response


def create_rate_limiter() -> RateLimitMiddleware:
    """Create a configured three-tier rate limiter."""
    return RateLimitMiddleware(app=None)
