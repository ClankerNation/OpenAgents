"""Rate limiting middleware for the OpenAgents API.

Implements a Redis-backed sliding-window rate limiter with a thread-safe
in-memory fallback that activates automatically when Redis is unreachable.
"""

import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Deque, Optional, Tuple

logger = logging.getLogger("openagents.ratelimit")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# In-memory sliding-window fallback (thread-safe)
# ---------------------------------------------------------------------------

class InMemoryRateLimiter:
    """Sliding-window rate limiter backed by per-IP timestamp deques.

    Every incoming request appends ``time.time()`` to the client's deque.
    Expired entries beyond the window are pruned on each check.  A global
    ``threading.Lock`` serialises all mutations so the structure is safe
    under concurrent access from multiple ASGI worker threads.
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._lock = threading.Lock()
        self._windows: Dict[str, Deque[float]] = defaultdict(deque)

    def is_rate_limited(self, client_ip: str) -> Tuple[bool, int]:
        now = time.time()
        cutoff = now - self.config.window_seconds

        with self._lock:
            window = self._windows[client_ip]

            # Prune expired timestamps from the left
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) >= self.config.requests_per_window:
                # Earliest non-expired entry determines retry delay
                retry_after = int(window[0] - cutoff) + 1
                return True, max(retry_after, 1)

            window.append(now)
            remaining = self.config.requests_per_window - len(window)
            return False, remaining

    def reset(self) -> None:
        """Clear all tracked state (useful in tests)."""
        with self._lock:
            self._windows.clear()


# ---------------------------------------------------------------------------
# Redis-backed sliding-window rate limiter
# ---------------------------------------------------------------------------

class RedisRateLimiter:
    """Sliding-window rate limiter using a Redis sorted set per client IP.

    Each request adds a timestamped member to a sorted set keyed by IP.
    Expired members are pruned with ``ZREMRANGEBYSCORE`` and the set size
    is compared against the configured limit.  The key is given a TTL
    equal to the window duration so stale keys are garbage-collected
    automatically.

    Parameters
    ----------
    redis_client:
        A ``redis.Redis`` (or compatible) instance.  May be ``None`` to
        start directly in fallback mode.
    config:
        Rate-limit parameters.
    """

    def __init__(self, redis_client, config: RateLimitConfig):
        self.redis = redis_client
        self.config = config

    def is_rate_limited(self, client_ip: str) -> Tuple[bool, int]:
        """Evaluate the rate limit via Redis sorted-set operations.

        Raises ``ConnectionError`` or ``TimeoutError`` (or any subclass)
        if the Redis connection is unavailable so the caller can fall back
        to the in-memory guard.
        """
        now = time.time()
        cutoff = now - self.config.window_seconds
        key = f"ratelimit:{client_ip}"

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.zadd(key, {f"{now}": now})
        pipe.zcard(key)
        pipe.expire(key, self.config.window_seconds)
        _, _, count, _ = pipe.execute()

        if count > self.config.requests_per_window:
            # Fetch the oldest surviving entry to compute retry delay
            oldest = self.redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = int(oldest[0][1] - cutoff) + 1
            else:
                retry_after = self.config.window_seconds
            return True, max(retry_after, 1)

        remaining = self.config.requests_per_window - count
        return False, remaining


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces per-IP rate limits.

    Uses ``RedisRateLimiter`` as the primary backend and falls back to
    ``InMemoryRateLimiter`` automatically when Redis raises a connection
    or timeout error.  A warning is logged on every fallback activation
    so operators can monitor Redis health.
    """

    def __init__(
        self,
        app,
        config: RateLimitConfig = None,
        redis_client=None,
    ):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self._redis_limiter: Optional[RedisRateLimiter] = None
        if redis_client is not None:
            self._redis_limiter = RedisRateLimiter(redis_client, self.config)
        self._memory_limiter = InMemoryRateLimiter(self.config)

    # ------------------------------------------------------------------
    # Client IP resolution
    # ------------------------------------------------------------------

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    # ------------------------------------------------------------------
    # Rate-limit evaluation with Redis → memory fallback
    # ------------------------------------------------------------------

    def _is_rate_limited(self, client_ip: str) -> Tuple[bool, int]:
        if self._redis_limiter is not None:
            try:
                return self._redis_limiter.is_rate_limited(client_ip)
            except (ConnectionError, TimeoutError, OSError) as exc:
                logger.warning(
                    "Redis unavailable — activating in-memory rate-limit "
                    "fallback: %s",
                    exc,
                )
            except Exception as exc:
                # Catch any unexpected redis-py exception so the request
                # is never dropped with a 500.
                logger.warning(
                    "Unexpected Redis error — activating in-memory rate-limit "
                    "fallback: %s",
                    exc,
                )

        return self._memory_limiter.is_rate_limited(client_ip)

    # ------------------------------------------------------------------
    # ASGI dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        is_limited, value = self._is_rate_limited(client_ip)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": value,
                },
                headers={"Retry-After": str(value)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        response.headers["X-RateLimit-Limit"] = str(self.config.requests_per_window)
        return response


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
    redis_client=None,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config, redis_client=redis_client)
