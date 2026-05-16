# Contributor metadata for CI traceability:
# Agent name: partyplatter08-lab
# Platform initialization text: System and developer initialization text is not
# reproduced because it is not user-visible. Public task initialization: build a
# local PR candidate for ClankerNation/OpenAgents#200 without external
# submission, contact, credential disclosure, or live-service interaction.
# Runtime environment:
# - OS: Linux 6.8.0-111-generic
# - arch: x86_64
# - working_directory:
#   /home/lando/.openclaw/workspace-bounty-scout/auto-work/
#   2026-05-16T22-00-55-638Z-clankernation-openagents-200/OpenAgents
# - shell: bash
"""Rate limiting middleware for the OpenAgents API."""

import hashlib
import math
import os
import time
from collections import defaultdict
from enum import Enum
from typing import Dict, Iterable, Optional, Tuple

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitTier(Enum):
    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    PREMIUM = "premium"


class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: Optional[int] = None,
        window_seconds: int = 60,
        burst_limit: int = 20,
        anonymous_requests_per_window: Optional[int] = None,
        authenticated_requests_per_window: int = 300,
        premium_requests_per_window: int = 1000,
        authenticated_api_keys: Optional[Iterable[str]] = None,
        premium_api_keys: Optional[Iterable[str]] = None,
        premium_api_key_prefixes: Tuple[str, ...] = ("pk_", "premium_"),
    ):
        anonymous_limit = (
            anonymous_requests_per_window
            if anonymous_requests_per_window is not None
            else requests_per_window
        )
        if anonymous_limit is None:
            anonymous_limit = 60

        # Legacy callers read requests_per_window and pass burst_limit, so keep
        # both attributes even though tiered limiting uses explicit per-tier
        # limits.
        self.requests_per_window = anonymous_limit
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.anonymous_requests_per_window = anonymous_limit
        self.authenticated_requests_per_window = authenticated_requests_per_window
        self.premium_requests_per_window = premium_requests_per_window
        self.authenticated_api_keys = set(authenticated_api_keys or ())
        self.premium_api_keys = set(premium_api_keys or ())
        self.premium_api_key_prefixes = premium_api_key_prefixes

    def limit_for_tier(self, tier: RateLimitTier) -> int:
        if tier is RateLimitTier.PREMIUM:
            return self.premium_requests_per_window
        if tier is RateLimitTier.AUTHENTICATED:
            return self.authenticated_requests_per_window
        return self.anonymous_requests_per_window


_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.jwt_secret = os.getenv("JWT_SECRET")
        self.authenticated_api_keys = self.config.authenticated_api_keys | _env_key_set(
            "AUTHENTICATED_API_KEYS"
        )
        self.premium_api_keys = self.config.premium_api_keys | _env_key_set(
            "PREMIUM_API_KEYS"
        )

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_request_tier(self, request: Request) -> Tuple[RateLimitTier, str]:
        state_tier = self._tier_from_request_state(request)
        if state_tier:
            return state_tier

        api_key = self._extract_api_key(request)
        if api_key:
            tier = self._tier_for_api_key(api_key)
            if tier:
                return tier, f"apikey:{_stable_digest(api_key)}"

        token = self._extract_bearer_token(request)
        if token:
            jwt_tier = self._tier_from_jwt(token)
            if jwt_tier:
                return jwt_tier

        return RateLimitTier.ANONYMOUS, f"ip:{self._get_client_ip(request)}"

    def _tier_from_request_state(
        self, request: Request
    ) -> Optional[Tuple[RateLimitTier, str]]:
        rate_limit_tier = getattr(request.state, "rate_limit_tier", None)
        if rate_limit_tier:
            tier = _coerce_tier(rate_limit_tier)
            identifier = getattr(request.state, "rate_limit_identifier", None)
            if tier and identifier:
                return tier, f"state:{identifier}"

        user = getattr(request.state, "user", None) or getattr(
            request.state, "current_user", None
        )
        if not user:
            return None

        user_id = _lookup(user, "id", "sub", "user_id", "address") or "authenticated"
        if _is_premium_identity(user):
            return RateLimitTier.PREMIUM, f"user:{user_id}"
        return RateLimitTier.AUTHENTICATED, f"user:{user_id}"

    def _extract_api_key(self, request: Request) -> Optional[str]:
        api_key = request.headers.get("X-API-Key") or request.headers.get(
            "X-OpenAgents-API-Key"
        )
        if api_key:
            return api_key.strip()

        auth_header = request.headers.get("Authorization", "")
        scheme, _, credentials = auth_header.partition(" ")
        if scheme.lower() in {"apikey", "api-key"} and credentials:
            return credentials.strip()
        return None

    def _extract_bearer_token(self, request: Request) -> Optional[str]:
        auth_header = request.headers.get("Authorization", "")
        scheme, _, credentials = auth_header.partition(" ")
        if scheme.lower() == "bearer" and credentials:
            return credentials.strip()
        return None

    def _tier_for_api_key(self, api_key: str) -> Optional[RateLimitTier]:
        if api_key in self.premium_api_keys:
            return RateLimitTier.PREMIUM
        if api_key in self.authenticated_api_keys:
            return RateLimitTier.AUTHENTICATED
        if self.authenticated_api_keys or self.premium_api_keys:
            return None
        if api_key.startswith(self.config.premium_api_key_prefixes):
            return RateLimitTier.PREMIUM
        return RateLimitTier.AUTHENTICATED

    def _tier_from_jwt(self, token: str) -> Optional[Tuple[RateLimitTier, str]]:
        if not self.jwt_secret:
            return None
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return None

        user_id = _lookup(payload, "sub", "id", "user_id", "address")
        if not user_id:
            return None

        if _is_premium_identity(payload):
            return RateLimitTier.PREMIUM, f"user:{user_id}"
        return RateLimitTier.AUTHENTICATED, f"user:{user_id}"

    def _is_rate_limited(self, client_ip: str) -> Tuple[bool, int]:
        """Legacy compatibility wrapper for callers that rate-limit by IP only."""
        is_limited, remaining, _reset_at, retry_after = self._check_rate_limit(
            f"legacy:ip:{client_ip}",
            self.config.requests_per_window,
        )
        return is_limited, retry_after if is_limited else remaining

    def _check_rate_limit(self, key: str, limit: int) -> Tuple[bool, int, int, int]:
        global _request_counts
        count, window_start = _request_counts[key]
        now = time.time()

        if now - window_start >= self.config.window_seconds:
            count = 0
            window_start = now

        reset_time = window_start + self.config.window_seconds
        reset_at = math.ceil(reset_time)
        retry_after = max(1, math.ceil(reset_time - now))

        if count >= limit:
            return True, 0, reset_at, retry_after

        count += 1
        _request_counts[key] = (count, window_start)
        remaining = max(0, limit - count)
        return False, remaining, reset_at, retry_after

    async def dispatch(self, request: Request, call_next):
        tier, identifier = self._get_request_tier(request)
        limit = self.config.limit_for_tier(tier)
        is_limited, remaining, reset_at, retry_after = self._check_rate_limit(
            f"{tier.value}:{identifier}",
            limit,
        )

        if is_limited:
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
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response


def create_rate_limiter(
    requests_per_minute: Optional[int] = None,
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


def _env_key_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {key.strip() for key in raw.split(",") if key.strip()}


def _stable_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _coerce_tier(value) -> Optional[RateLimitTier]:
    if isinstance(value, RateLimitTier):
        return value
    if isinstance(value, str):
        normalized = value.lower()
        for tier in RateLimitTier:
            if tier.value == normalized:
                return tier
    return None


def _lookup(source, *keys: str):
    for key in keys:
        if isinstance(source, dict):
            value = source.get(key)
        else:
            value = getattr(source, key, None)
        if value:
            return value
    return None


def _is_premium_identity(identity) -> bool:
    if _lookup(identity, "premium", "is_premium"):
        return True

    tier = _lookup(identity, "tier", "plan", "subscription")
    if isinstance(tier, str) and tier.lower() == "premium":
        return True

    roles = _lookup(identity, "roles", "scopes") or []
    if isinstance(roles, str):
        roles = [roles]
    return any(str(role).lower() == "premium" for role in roles)
