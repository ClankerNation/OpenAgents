# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow

"""Rate limiting middleware for the OpenAgents API with sliding window and persistent storage."""

import os
import time
import json
import sqlite3
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Optional, List, Tuple


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


# Per-endpoint rate limit configurations
ENDPOINT_LIMITS: Dict[str, RateLimitConfig] = {
    "/auth/login": RateLimitConfig(requests_per_window=10, window_seconds=60),
    "/auth/refresh": RateLimitConfig(requests_per_window=20, window_seconds=60),
    "/agents": RateLimitConfig(requests_per_window=60, window_seconds=60),
    "/tasks": RateLimitConfig(requests_per_window=60, window_seconds=60),
    "/reputation": RateLimitConfig(requests_per_window=30, window_seconds=60),
    "default": RateLimitConfig(requests_per_window=100, window_seconds=60),
}

# Trusted proxy IPs that are allowed to set X-Forwarded-For
TRUSTED_PROXIES = set(
    os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1").split(",")
)

# SQLite database path for persistent rate limiting
DB_PATH = os.getenv("RATELIMIT_DB_PATH", "./ratelimit.db")


def _init_db():
    """Initialize SQLite database for persistent rate limit storage."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_limit_entries (
            client_ip TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rate_limit_lookup 
        ON rate_limit_entries(client_ip, endpoint, timestamp)
    """)
    conn.commit()
    conn.close()


_init_db()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.default_config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP with trusted proxy validation.
        
        Only trusts X-Forwarded-For if the direct connection is from a trusted proxy.
        Otherwise uses the direct connection IP to prevent header spoofing.
        """
        direct_ip = request.client.host if request.client else "unknown"
        
        # Only trust X-Forwarded-For if direct connection is from trusted proxy
        if direct_ip in TRUSTED_PROXIES:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                # Take the leftmost IP (original client) from the chain
                return forwarded.split(",")[0].strip()
        
        return direct_ip

    def _get_endpoint_config(self, path: str) -> RateLimitConfig:
        """Get rate limit config for specific endpoint or default."""
        # Check exact match first
        if path in ENDPOINT_LIMITS:
            return ENDPOINT_LIMITS[path]
        
        # Check prefix matches
        for endpoint, config in ENDPOINT_LIMITS.items():
            if endpoint != "default" and path.startswith(endpoint):
                return config
        
        return ENDPOINT_LIMITS.get("default", self.default_config)

    def _is_rate_limited_sliding_window(
        self, client_ip: str, endpoint: str, config: RateLimitConfig
    ) -> Tuple[bool, int, int]:
        """Check rate limit using sliding window algorithm with SQLite persistence.
        
        Returns: (is_limited, retry_after_seconds, remaining_requests)
        """
        now = time.time()
        window_start = now - config.window_seconds
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            # Clean old entries outside the window
            cursor.execute(
                "DELETE FROM rate_limit_entries WHERE client_ip = ? AND endpoint = ? AND timestamp < ?",
                (client_ip, endpoint, window_start)
            )
            
            # Count requests in current window
            cursor.execute(
                "SELECT COUNT(*) FROM rate_limit_entries WHERE client_ip = ? AND endpoint = ? AND timestamp >= ?",
                (client_ip, endpoint, window_start)
            )
            count = cursor.fetchone()[0]
            
            if count >= config.requests_per_window:
                # Find oldest entry in window to calculate retry-after
                cursor.execute(
                    "SELECT MIN(timestamp) FROM rate_limit_entries WHERE client_ip = ? AND endpoint = ? AND timestamp >= ?",
                    (client_ip, endpoint, window_start)
                )
                oldest = cursor.fetchone()[0]
                retry_after = int((oldest + config.window_seconds) - now) + 1
                conn.commit()
                return True, max(retry_after, 1), 0
            
            # Add new entry
            cursor.execute(
                "INSERT INTO rate_limit_entries (client_ip, endpoint, timestamp) VALUES (?, ?, ?)",
                (client_ip, endpoint, now)
            )
            conn.commit()
            
            remaining = config.requests_per_window - count - 1
            return False, 0, remaining
            
        finally:
            conn.close()

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        endpoint = request.url.path
        config = self._get_endpoint_config(endpoint)
        
        is_limited, retry_after, remaining = self._is_rate_limited_sliding_window(
            client_ip, endpoint, config
        )

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMITED",
                    "message": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(config.requests_per_window),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(config.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(config.window_seconds)
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
