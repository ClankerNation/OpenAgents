"""Rate limiting middleware for the OpenAgents API.

Fix traceability:
@fix-author claude-code-b3ar-sudo
@runtime linux x86_64, Claude Code; private paths and hidden session payload intentionally omitted.
@timestamp 2026-05-20T00:00:00Z
"""

from __future__ import annotations

import ipaddress
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Dict, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


@dataclass(frozen=True)
class EndpointLimit:
    requests_per_window: int
    window_seconds: int


@dataclass
class RateLimitConfig:
    requests_per_window: int = 100
    window_seconds: int = 60
    burst_limit: int = 20
    storage_path: str = field(
        default_factory=lambda: os.getenv("RATE_LIMIT_DB_PATH", "/tmp/openagents-rate-limit.sqlite3")
    )
    trusted_proxy_cidrs: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            cidr.strip() for cidr in os.getenv("TRUSTED_PROXY_CIDRS", "").split(",") if cidr.strip()
        )
    )
    endpoint_limits: Dict[str, EndpointLimit] = field(default_factory=dict)


class SQLiteSlidingWindowStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS rate_limit_events ("
                "key TEXT NOT NULL, "
                "occurred_at REAL NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rate_limit_events_key_time "
                "ON rate_limit_events(key, occurred_at)"
            )

    def hit(self, key: str, now: float, window_seconds: int, limit: int) -> Tuple[bool, int, int]:
        cutoff = now - window_seconds
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM rate_limit_events WHERE occurred_at < ?", (cutoff,))
            count = conn.execute(
                "SELECT COUNT(*) FROM rate_limit_events WHERE key = ? AND occurred_at >= ?",
                (key, cutoff),
            ).fetchone()[0]

            if count >= limit:
                oldest = conn.execute(
                    "SELECT MIN(occurred_at) FROM rate_limit_events WHERE key = ? AND occurred_at >= ?",
                    (key, cutoff),
                ).fetchone()[0]
                retry_after = max(1, int((oldest + window_seconds) - now) + 1)
                return True, retry_after, 0

            conn.execute(
                "INSERT INTO rate_limit_events(key, occurred_at) VALUES (?, ?)",
                (key, now),
            )
            remaining = max(0, limit - count - 1)
            return False, remaining, limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.store = SQLiteSlidingWindowStore(self.config.storage_path)
        self.trusted_proxy_networks = tuple(
            ipaddress.ip_network(cidr, strict=False) for cidr in self.config.trusted_proxy_cidrs
        )

    def _is_trusted_proxy(self, host: str) -> bool:
        if not host:
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(address in network for network in self.trusted_proxy_networks)

    def _get_client_ip(self, request: Request) -> str:
        direct_host = request.client.host if request.client else "unknown"
        if not self._is_trusted_proxy(direct_host):
            return direct_host

        forwarded = request.headers.get("X-Forwarded-For")
        if not forwarded:
            return direct_host

        for candidate in (part.strip() for part in forwarded.split(",") if part.strip()):
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            return candidate
        return direct_host

    def _limit_for_path(self, path: str) -> EndpointLimit:
        if path in self.config.endpoint_limits:
            return self.config.endpoint_limits[path]
        matching_prefixes = [prefix for prefix in self.config.endpoint_limits if prefix.endswith("*")]
        for prefix in sorted(matching_prefixes, key=len, reverse=True):
            if path.startswith(prefix[:-1]):
                return self.config.endpoint_limits[prefix]
        return EndpointLimit(self.config.requests_per_window, self.config.window_seconds)

    def _is_rate_limited(self, client_ip: str, path: str) -> Tuple[bool, int, int]:
        limit = self._limit_for_path(path)
        key = f"{client_ip}:{path}"
        return self.store.hit(key, time.time(), limit.window_seconds, limit.requests_per_window)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        is_limited, value, limit = self._is_rate_limited(client_ip, request.url.path)

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
        response.headers["X-RateLimit-Limit"] = str(limit)
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
