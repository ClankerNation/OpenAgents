r"""
AGENT: Gemini CLI
PLATFORM: win32 | Monday, 18 May 2026
ENVIRONMENT: win32 | x64 | C:\Users\aalok\OpenAgents | powershell
TASK: Reworked ratelimit.py with Auth-awareness, IP-Spoofing protection, and Backwards Compatibility (#200)
"""

import time
import os
import jwt
import logging
import asyncio
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional, List

# Setup logging
logger = logging.getLogger("ratelimit")


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
        
        # Default Tier Limits: (requests_per_window, burst_limit)
        self.tiers = {
            "anonymous": (60, 10),
            "authenticated": (300, 50),
            "premium": (1000, 100)
        }


# Sliding window storage: client_id -> [timestamps]
_request_history: Dict[str, List[float]] = defaultdict(list)
# Lock for thread-safety in async environments
_history_lock = asyncio.Lock()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        # Secure secret handling
        self.jwt_secret = os.environ.get("JWT_SECRET", "fallback_secret_for_dev_only")

    def _get_client_identity(self, request: Request) -> Tuple[str, str]:
        """
        Determines client identity and their rate limit tier.
        Returns (identity_key, tier)
        """
        # 1. Check for Premium API Key (Highest Priority)
        premium_key = request.headers.get("X-Premium-Key")
        if premium_key:
            return f"premium:{premium_key}", "premium"

        # 2. Check for Authenticated User
        # First check if user was already identified by a previous middleware
        user = getattr(request.state, "user", None)
        if user and isinstance(user, dict) and user.get("id"):
            return f"user:{user['id']}", "authenticated"
            
        # Proactive JWT check to identify tier before route dependencies run
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                # We verify signature to prevent tier elevation attacks.
                payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
                user_id = payload.get("sub") or payload.get("id")
                if user_id:
                    return f"user:{user_id}", "authenticated"
            except Exception:
                pass

        # 3. Fallback to IP for Anonymous
        trust_proxy = os.getenv("TRUST_PROXY", "false").lower() == "true"
        if trust_proxy:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
            else:
                ip = request.client.host if request.client else "unknown"
        else:
            ip = request.client.host if request.client else "unknown"
            
        return f"anon:{ip}", "anonymous"

    async def _is_rate_limited(self, identity_key: str, tier: str) -> Tuple[bool, int, int, int]:
        """
        Dual-window sliding rate limit check (Burst + Total).
        Returns (is_limited, limit, remaining, reset_in_seconds)
        """
        global _request_history
        now = time.time()
        
        # Resolve limits for the detected tier
        tier_limits = self.config.tiers.get(tier)
        if tier_limits:
            limit, burst = tier_limits
        else:
            limit = self.config.requests_per_window
            burst = self.config.burst_limit
            
        async with _history_lock:
            history = _request_history[identity_key]

            # Cleanup: Remove expired timestamps outside the main window
            history = [ts for ts in history if now - ts < self.config.window_seconds]
            
            # 1. Check Burst Limit (1 second sub-window)
            burst_history = [ts for ts in history if now - ts < 1.0]
            if len(burst_history) >= burst:
                _request_history[identity_key] = history
                return True, limit, 0, 1

            # 2. Check Total Window Limit
            if len(history) >= limit:
                reset_in = int(self.config.window_seconds - (now - history[0]))
                reset_in = max(1, reset_in)
                _request_history[identity_key] = history
                return True, limit, 0, reset_in

            # Allowance granted. Record current request.
            history.append(now)
            _request_history[identity_key] = history
            
            remaining = limit - len(history)
            reset_in = int(self.config.window_seconds - (now - history[0]))
            reset_in = max(1, reset_in)

            return False, limit, remaining, reset_in

    async def dispatch(self, request: Request, call_next):
        # Health checks are excluded from limiting to ensure infra stability
        if request.url.path.endswith("/health"):
            return await call_next(request)

        identity_key, tier = self._get_client_identity(request)
        is_limited, limit, remaining, reset = await self._is_rate_limited(identity_key, tier)

        # Standard X-RateLimit headers (Reset as Epoch UTC)
        reset_at = int(time.time() + reset)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": reset,
                    "message": f"Rate limit reached for {tier} tier. Please try again later."
                },
                headers={
                    "Retry-After": str(reset),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                    "X-RateLimit-Tier": tier
                },
            )

        response = await call_next(request)
        
        # Inject standard rate limit headers into successful response
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        response.headers["X-RateLimit-Tier"] = tier
        
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    """
    Backwards compatible factory for creating the rate limiter middleware.
    """
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
