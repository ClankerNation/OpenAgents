"""Rate limiting middleware for OpenAgents API with auth-aware tiers."""

import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


ANONYMOUS_LIMIT = 60
AUTHENTICATED_LIMIT = 300
PREMIUM_LIMIT = 1000
WINDOW_SECONDS = 60

# key -> (count, window_start_epoch)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def _get_client_ip(self, request: Request) -> str:
        # Keep backwards compatibility with deployments that pass through proxy headers.
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_tier(self, request: Request) -> str:
        api_key = request.headers.get("X-Api-Key", "")
        auth_header = request.headers.get("Authorization", "")

        # Premium: explicit premium key convention used in existing bounty examples.
        if api_key.endswith("_premium"):
            return "premium"

        # Authenticated: any present auth signal.
        if api_key or auth_header:
            return "authenticated"

        return "anonymous"

    def _get_limit_for_tier(self, tier: str) -> int:
        if tier == "premium":
            return PREMIUM_LIMIT
        if tier == "authenticated":
            return AUTHENTICATED_LIMIT
        return ANONYMOUS_LIMIT

    def _build_bucket_key(self, request: Request, tier: str) -> str:
        client_ip = self._get_client_ip(request)

        # keep independent counters by tier to avoid cross-tier bleed-through
        auth_hint = request.headers.get("X-Api-Key") or request.headers.get("Authorization") or "anon"
        return f"{tier}:{client_ip}:{auth_hint}"

    def _check_and_incr(self, key: str, limit: int) -> Tuple[bool, int, int]:
        global _request_counts
        count, window_start = _request_counts[key]
        now = time.time()

        if now - window_start >= WINDOW_SECONDS:
            count = 0
            window_start = now

        if count >= limit:
            retry_after = max(1, int(WINDOW_SECONDS - (now - window_start)))
            reset_epoch = int(window_start + WINDOW_SECONDS)
            return True, retry_after, reset_epoch

        count += 1
        _request_counts[key] = (count, window_start)
        remaining = max(0, limit - count)
        reset_epoch = int(window_start + WINDOW_SECONDS)
        return False, remaining, reset_epoch

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(ANONYMOUS_LIMIT)
            response.headers["X-RateLimit-Remaining"] = str(ANONYMOUS_LIMIT)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + WINDOW_SECONDS)
            return response

        tier = self._get_tier(request)
        limit = self._get_limit_for_tier(tier)
        key = self._build_bucket_key(request, tier)

        is_limited, value, reset_epoch = self._check_and_incr(key, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                    "tier": tier,
                },
                headers={
                    "Retry-After": str(value),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_epoch),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Reset"] = str(reset_epoch)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    # Preserve function signature for backwards compatibility with existing imports.
    _ = requests_per_minute
    _ = burst
    return RateLimitMiddleware(app=None)
