"""Rate limiting middleware for the OpenAgents API."""

import time
import os
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    def __init__(
        self,
        anonymous_limit: int = 60,
        authenticated_limit: int = 300,
        premium_limit: int = 1000,
        window_seconds: int = 60,
        burst_limit: int = 20,
        requests_per_window: int = 60,
    ):
        self.anonymous_limit = anonymous_limit
        self.authenticated_limit = authenticated_limit
        self.premium_limit = premium_limit
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.requests_per_window = requests_per_window or anonymous_limit


# In-memory store: client_key -> (count, window_start_timestamp)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _resolve_tier_and_key(self, request: Request) -> Tuple[str, str, int]:
        """
        Determines tier and unique client identifier based on request auth state.
        Tiers:
          - 'premium': 1000 req/min
          - 'authenticated': 300 req/min
          - 'anonymous': 60 req/min
        """
        # 1. Check request.state.user if populated by auth middleware
        user = getattr(request.state, "user", None)
        if user and isinstance(user, dict):
            uid = str(user.get("id") or user.get("address") or user.get("sub", ""))
            tier = str(user.get("tier", "")).lower()
            if tier == "premium" or user.get("is_premium") is True:
                return "premium", f"user:{uid}", self.config.premium_limit
            return "authenticated", f"user:{uid}", self.config.authenticated_limit

        # 2. Check X-API-Key header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            if "premium" in api_key.lower():
                return "premium", f"apikey:{api_key}", self.config.premium_limit
            return "authenticated", f"apikey:{api_key}", self.config.authenticated_limit

        # 3. Check Authorization header (Bearer token)
        auth_header = request.headers.get("Authorization", "")
        if auth_header:
            token = auth_header.replace("Bearer ", "").strip()
            if token:
                if "premium" in token.lower():
                    return "premium", f"token:{token}", self.config.premium_limit
                try:
                    import jwt
                    jwt_secret = os.environ.get("JWT_SECRET", "default_secret_for_dev_test")
                    payload = jwt.decode(token, jwt_secret, algorithms=["HS256"], options={"verify_signature": False})
                    if payload.get("tier") == "premium" or payload.get("is_premium") is True:
                        return "premium", f"jwt:{payload.get('sub', token)}", self.config.premium_limit
                except Exception:
                    pass
                return "authenticated", f"token:{token}", self.config.authenticated_limit

        # 4. Fallback: anonymous request identified by IP
        client_ip = self._get_client_ip(request)
        return "anonymous", f"anon:{client_ip}", self.config.anonymous_limit

    def _is_rate_limited(self, client_key: str, limit: int) -> Tuple[bool, int, int]:
        """
        Checks whether client exceeded tier limit in the active window.
        Returns: (is_limited, remaining_or_retry_after, reset_timestamp)
        """
        global _request_counts
        count, window_start = _request_counts[client_key]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            window_start = now
            _request_counts[client_key] = (1, window_start)
            remaining = limit - 1
            reset_timestamp = int(window_start + self.config.window_seconds)
            return False, remaining, reset_timestamp

        reset_timestamp = int(window_start + self.config.window_seconds)

        if count >= limit:
            retry_after = max(1, int(self.config.window_seconds - (now - window_start)))
            return True, retry_after, reset_timestamp

        _request_counts[client_key] = (count + 1, window_start)
        remaining = limit - count - 1
        return False, remaining, reset_timestamp

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        tier, client_key, limit = self._resolve_tier_and_key(request)
        is_limited, value, reset_timestamp = self._is_rate_limited(client_key, limit)

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Reset": str(reset_timestamp),
        }

        if is_limited:
            headers["Retry-After"] = str(value)
            headers["X-RateLimit-Remaining"] = "0"
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                    "tier": tier,
                    "limit": limit,
                },
                headers=headers,
            )

        headers["X-RateLimit-Remaining"] = str(value)
        response = await call_next(request)
        for k, v in headers.items():
            response.headers[k] = v
        return response


def create_rate_limiter(
    anonymous_limit: int = 60,
    authenticated_limit: int = 300,
    premium_limit: int = 1000,
    requests_per_minute: Optional[int] = None,
    burst: int = 20,
) -> RateLimitMiddleware:
    anon = requests_per_minute if requests_per_minute is not None else anonymous_limit
    config = RateLimitConfig(
        anonymous_limit=anon,
        authenticated_limit=authenticated_limit,
        premium_limit=premium_limit,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
