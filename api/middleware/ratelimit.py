/**
 * @contributor oocheol
 * @platform Interactive Engineering Agent specializing in surgical codebase modifications and high-integrity PR submissions. Core mandates: Security (protecting credentials/.env), Efficiency (minimizing context/tokens), and Engineering Excellence (idiomatic code, exhaustive testing, and non-destructive changes). Operating under a Research-Strategy-Execution lifecycle with a Plan-Act-Validate execution loop.
 * @runtime os=win32, arch=x64, working_directory=C:\chromeMCP\OpenAgents
 * @date 2026-05-19T10:30:00Z
 *
 * Robust rate limiting middleware with sliding window algorithm and SQLite persistence.
 */

import time
import sqlite3
import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Tuple, Dict

DB_PATH = os.path.join(os.getcwd(), "ratelimit.db")

class RateLimitConfig:
    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        per_endpoint: Dict[str, int] = None
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.per_endpoint = per_endpoint or {}

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                client_id TEXT,
                endpoint TEXT,
                timestamp REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_client_endpoint ON request_logs(client_id, endpoint, timestamp)")
        conn.close()

    def _get_client_id(self, request: Request) -> str:
        # SECURITY: Block spoofable X-Forwarded-For. 
        # Only trust it if we are behind a known proxy. 
        # For this bounty, we use the direct connection IP as the primary truth.
        return request.client.host if request.client else "127.0.0.1"

    def _is_rate_limited(self, client_id: str, endpoint: str) -> Tuple[bool, int, int]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        now = time.time()
        window_start = now - self.config.window_seconds
        
        # Clean old logs (Sliding Window maintenance)
        cursor.execute("DELETE FROM request_logs WHERE timestamp < ?", (window_start,))
        
        # Check current count for this client on this endpoint
        limit = self.config.per_endpoint.get(endpoint, self.config.requests_per_window)
        
        cursor.execute(
            "SELECT COUNT(*) FROM request_logs WHERE client_id = ? AND endpoint = ? AND timestamp >= ?",
            (client_id, endpoint, window_start)
        )
        count = cursor.fetchone()[0]
        
        if count >= limit:
            # Get the oldest timestamp in the current window to calculate retry_after
            cursor.execute(
                "SELECT MIN(timestamp) FROM request_logs WHERE client_id = ? AND endpoint = ?",
                (client_id, endpoint)
            )
            oldest = cursor.fetchone()[0]
            retry_after = int(self.config.window_seconds - (now - oldest))
            conn.close()
            return True, max(1, retry_after), limit - count

        # Record new request
        cursor.execute(
            "INSERT INTO request_logs (client_id, endpoint, timestamp) VALUES (?, ?, ?)",
            (client_id, endpoint, now)
        )
        conn.commit()
        conn.close()
        
        return False, 0, limit - count - 1

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_id = self._get_client_id(request)
        endpoint = request.url.path
        
        is_limited, retry_after, remaining = self._is_rate_limited(client_id, endpoint)
        
        limit = self.config.per_endpoint.get(endpoint, self.config.requests_per_window)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests to {endpoint}. Please try again later.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after)
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response

def create_rate_limiter(
    requests_per_minute: int = 100,
    per_endpoint_overrides: Dict[str, int] = None
) -> RateLimitMiddleware:
    config = RateLimitConfig(
        requests_per_window=requests_per_minute,
        window_seconds=60,
        per_endpoint=per_endpoint_overrides
    )
    return RateLimitMiddleware(app=None, config=config)
