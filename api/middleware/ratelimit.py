r"""
AGENT: Gemini CLI
PLATFORM: win32 | Sunday, 17 May 2026
TASK: Reworked ratelimit.py with JWT awareness, Burst limits, and Epoch timestamps (#200)
"""

import time
import os
import jwt
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional, List

# JWT Configuration (for proactive decoding)
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key")
JWT_ALGORITHM = "HS256"

class RateLimitConfig:
    def __init__(
        self,
        requests_per_minute: int = 100,
        burst_limit: int = 20,
    ):
        self.window_seconds = 60
        self.burst_seconds = 1
        
        # Tiers: (min_limit, burst_limit)
        self.tiers = {
            "anonymous": (60, 10),
            "authenticated": (300, 50),
            "premium": (1000, 100)
        }
        
        # Override default authenticated limit if provided via constructor
        if requests_per_minute != 100:
            self.tiers["authenticated"] = (requests_per_minute, burst_limit)

# Storage: client_id -> [timestamps]
_request_history: Dict[str, List[float]] = defaultdict(list)

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_identity(self, request: Request) -> Tuple[str, str]:
        """
        Proactively detects tier using JWT decoding or headers.
        """
        # 1. Premium Header (Highest Priority)
        premium_key = request.headers.get("X-Premium-Key")
        if premium_key:
            return f"premium:{premium_key}", "premium"

        # 2. JWT Decoding (Proactive Auth Detection)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                user_id = payload.get("sub") or payload.get("id")
                if user_id:
                    return f"user:{user_id}", "authenticated"
            except (jwt.PyJWTError, IndexError):
                pass # Invalid token, fallback to IP

        # 3. Fallback to IP for Anonymous
        trust_proxy = os.getenv("TRUST_PROXY", "false").lower() == "true"
        if trust_proxy:
            forwarded = request.headers.get("X-Forwarded-For")
            ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        else:
            ip = request.client.host if request.client else "unknown"
            
        return f"anon:{ip}", "anonymous"

    def _check_rate_limit(self, identity_key: str, tier: str) -> Tuple[bool, int, int, int]:
        """
        Checks both the minute window and the burst window.
        Returns (is_limited, limit, remaining, reset_timestamp)
        """
        global _request_history
        now = time.time()
        limit, burst = self.config.tiers.get(tier, self.config.tiers["anonymous"])
        
        history = _request_history[identity_key]

        # 1. Sliding Window (60s)
        history = [ts for ts in history if now - ts < self.config.window_seconds]
        
        # 2. Burst Check (1s)
        burst_count = len([ts for ts in history if now - ts < self.config.burst_seconds])

        if len(history) >= limit:
            reset_ts = int(history[0] + self.config.window_seconds)
            _request_history[identity_key] = history
            return True, limit, 0, reset_ts

        if burst_count >= burst:
            reset_ts = int(now + self.config.burst_seconds)
            _request_history[identity_key] = history
            return True, limit, 0, reset_ts

        # Add current request
        history.append(now)
        _request_history[identity_key] = history
        
        remaining = limit - len(history)
        reset_ts = int(now + self.config.window_seconds) if not history else int(history[0] + self.config.window_seconds)

        return False, limit, remaining, reset_ts

    async def dispatch(self, request: Request, call_next):
        # Health checks bypass
        if request.url.path.endswith("/health"):
            return await call_next(request)

        identity_key, tier = self._get_client_identity(request)
        is_limited, limit, remaining, reset_ts = self._check_rate_limit(identity_key, tier)

        if is_limited:
            retry_after = max(1, int(reset_ts - time.time()))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "tier": tier,
                    "retry_after": retry_after,
                    "reset_at": reset_ts
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                    "X-RateLimit-Tier": tier
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        response.headers["X-RateLimit-Tier"] = tier
        return response

def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_minute=requests_per_minute,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
