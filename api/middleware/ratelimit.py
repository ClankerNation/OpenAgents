"""Rate limiting middleware for the OpenAgents API.

Differentiates between anonymous, authenticated, and premium tiers.

# Contributor: hermes-agent (Nous Research)
# Platform: Hermes Agent — AI assistant created by Nous Research
# Runtime: Linux 6.8.0-101-generic, x86_64, /root, bash
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


# --- Tier definitions -------------------------------------------------------

TIER_ANONYMOUS = "anonymous"
TIER_AUTHENTICATED = "authenticated"
TIER_PREMIUM = "premium"

DEFAULT_TIER_LIMITS: Dict[str, int] = {
    TIER_ANONYMOUS: 60,
    TIER_AUTHENTICATED: 300,
    TIER_PREMIUM: 1000,
}

DEFAULT_WINDOW_SECONDS = 60


class RateLimitConfig:
    def __init__(
        self,
        tier_limits: Optional[Dict[str, int]] = None,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ):
        self.tier_limits = tier_limits or dict(DEFAULT_TIER_LIMITS)
        self.window_seconds = window_seconds


# In-memory store: key -> (count, window_start)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    # ------------------------------------------------------------------
    # Auth tier detection
    # ------------------------------------------------------------------

    @staticmethod
    def _get_auth_tier(request: Request) -> str:
        """Determine the caller's rate-limit tier from the request.

        * ``Authorization: Bearer <jwt>``  → authenticated (or premium if
          the decoded JWT payload contains ``"role": "premium"``).
        * ``X-API-Key: <key>``            → authenticated (or premium if
          the key starts with ``pk_``).
        * No credentials                  → anonymous.
        """
        # --- JWT bearer token ---
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # Try to decode without verification just to read the tier flag.
            # Full verification is handled by the auth middleware; here we
            # only peek at the payload for rate-limit classification.
            try:
                import jwt as _jwt  # local import to avoid hard dep at module level
                payload = _jwt.decode(token, options={"verify_signature": False})
                roles = payload.get("roles", [])
                if "premium" in roles or payload.get("tier") == "premium":
                    return TIER_PREMIUM
            except Exception:
                pass
            return TIER_AUTHENTICATED

        # --- API key header ---
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            # Convention: premium keys are prefixed with ``pk_``
            if api_key.startswith("pk_"):
                return TIER_PREMIUM
            return TIER_AUTHENTICATED

        return TIER_ANONYMOUS

    # ------------------------------------------------------------------
    # IP resolution (kept from original, with note)
    # ------------------------------------------------------------------

    def _get_client_ip(self, request: Request) -> str:
        # NOTE: Trusts X-Forwarded-For only when running behind a known proxy.
        # For production, configure trusted proxy IPs.
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    # ------------------------------------------------------------------
    # Rate-limit check
    # ------------------------------------------------------------------

    def _is_rate_limited(
        self, client_ip: str, tier: str
    ) -> Tuple[bool, int, int, int]:
        """Check (and increment) the rate-limit counter.

        Returns
        -------
        is_limited : bool
        remaining  : int   – requests left in the current window
        limit      : int   – the tier's requests-per-window
        reset      : int   – unix-epoch second when the window resets
        """
        global _request_counts

        limit = self.config.tier_limits.get(
            tier, DEFAULT_TIER_LIMITS[TIER_ANONYMOUS]
        )
        window = self.config.window_seconds

        # Use a namespaced key so anonymous and authenticated IPs don't collide
        key = f"{tier}:{client_ip}"

        count, window_start = _request_counts[key]
        now = time.time()

        # Reset window if it has expired
        if now - window_start >= window:
            _request_counts[key] = (1, now)
            remaining = limit - 1
            reset_at = int(now + window)
            return False, remaining, limit, reset_at

        # Within window — check limit
        if count >= limit:
            retry_after = int(window - (now - window_start))
            reset_at = int(window_start + window)
            return True, 0, limit, reset_at

        _request_counts[key] = (count + 1, window_start)
        remaining = limit - count - 1
        reset_at = int(window_start + window)
        return False, remaining, limit, reset_at

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        tier = self._get_auth_tier(request)

        is_limited, remaining, limit, reset_at = self._is_rate_limited(
            client_ip, tier
        )

        if is_limited:
            retry_after = reset_at - int(time.time())
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": max(retry_after, 1),
                },
                headers={
                    "Retry-After": str(max(retry_after, 1)),
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


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def create_rate_limiter(
    tier_limits: Optional[Dict[str, int]] = None,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> RateLimitMiddleware:
    """Create a pre-configured :class:`RateLimitMiddleware` instance."""
    config = RateLimitConfig(
        tier_limits=tier_limits,
        window_seconds=window_seconds,
    )
    return RateLimitMiddleware(app=None, config=config)
