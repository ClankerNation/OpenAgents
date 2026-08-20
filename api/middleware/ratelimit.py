# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow

"""Rate limiting middleware for the OpenAgents API."""

import time
import os
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


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


# Per-endpoint configuration registry
_ENDPOINT_CONFIGS: Dict[str, RateLimitConfig] = {}


def configure_endpoint(path_prefix: str, config: RateLimitConfig) -> None:
    """Register a custom rate limit config for an endpoint prefix."""
    _ENDPOINT_CONFIGS[path_prefix] = config


class SlidingWindowStore:
    """Persistent sliding window rate limiter using SQLite for restart survival."""

    def __init__(self, db_path: str = "/tmp/openagents_ratelimit.db"):
        import sqlite3
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS rate_limits ("
            "key TEXT NOT NULL, timestamp REAL NOT NULL)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_rl_key_ts ON rate_limits(key, timestamp)")
        self.conn.commit()

    def is_allowed(self, key: str, limit: int, window_seconds: float) -> Tuple[bool, int]:
        now = time.time()
        cutoff = now - window_seconds

        # Clean old entries and count current window in one pass
        cursor = self.conn.execute(
            "DELETE FROM rate_limits WHERE key = ? AND timestamp < ?",
            (key, cutoff),
        )
        self.conn.commit()

        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM rate_limits WHERE key = ? AND timestamp >= ?",
            (key, cutoff),
        )
        count = cursor.fetchone()[0]

        if count >= limit:
            # Find oldest entry in window to calculate retry-after
            cursor = self.conn.execute(
                "SELECT MIN(timestamp) FROM rate_limits WHERE key = ? AND timestamp >= ?",
                (key, cutoff),
            )
            oldest = cursor.fetchone()[0] or now
            retry_after = max(1, int((oldest + window_seconds) - now))
            return False, retry_after

        self.conn.execute(
            "INSERT INTO rate_limits (key, timestamp) VALUES (?, ?)",
            (key, now),
        )
        self.conn.commit()
        remaining = limit - count - 1
        return True, remaining

    def close(self):
        self.conn.close()


# Global persistent store — survives restarts
_store = SlidingWindowStore()

# Trusted proxy IPs that are allowed to set X-Forwarded-For
_TRUSTED_PROXIES = {
    "127.0.0.1", "::1",
    # Add Cloudflare, AWS ALB, etc. as needed
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.default_config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        # Only trust X-Forwarded-For from known trusted proxies
        direct_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")

        if forwarded and direct_ip in _TRUSTED_PROXIES:
            # Take the leftmost IP (original client) after validating proxy
            parts = [p.strip() for p in forwarded.split(",")]
            return parts[0] if parts else direct_ip

        # Untrusted source — ignore X-Forwarded-For entirely
        return direct_ip

    def _get_config_for_path(self, path: str) -> RateLimitConfig:
        for prefix, cfg in _ENDPOINT_CONFIGS.items():
            if path.startswith(prefix):
                return cfg
        return self.default_config

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        config = self._get_config_for_path(request.url.path)
        key = f"{client_ip}:{request.url.path}"

        is_allowed, value = _store.is_allowed(
            key, config.requests_per_window, config.window_seconds
        )

        if not is_allowed:
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
        response.headers["X-RateLimit-Limit"] = str(config.requests_per_window)
        return response


def create_rate_limiter(
    requests_per_minute: int = 100,
    burst: int = 20,
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        burst_limit=burst,
    )
    return RateLimitMiddleware(app=None, config=config)
