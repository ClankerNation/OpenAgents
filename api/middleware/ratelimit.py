"""Rate limiting middleware for the OpenAgents API.
@contributor opencode-gaotax2006
@platform You are opencode, an interactive CLI tool...
@runtime os=win32 arch=x64 workingdir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
@date 2026-05-17T00:00:00Z
"""

import time
import json
import os
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple


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


STORAGE_FILE = os.environ.get("RATELIMIT_STORAGE_FILE", "ratelimit_store.json")
_request_counts: Dict[str, list] = defaultdict(list)


def _load_persisted():
    try:
        with open(STORAGE_FILE, "r") as f:
            data = json.load(f)
            for k, v in data.items():
                _request_counts[k] = v
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def _save_persisted():
    try:
        with open(STORAGE_FILE, "w") as f:
            json.dump(dict(_request_counts), f)
    except OSError:
        pass


_load_persisted()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            trusted_proxy = request.client.host if request.client else None
            if trusted_proxy and self._is_trusted_proxy(trusted_proxy):
                ips = [ip.strip() for ip in forwarded.split(",")]
                return ips[0] if ips else trusted_proxy
        return request.client.host if request.client else "unknown"

    def _is_trusted_proxy(self, ip: str) -> bool:
        trusted = os.environ.get("TRUSTED_PROXIES", "").split(",")
        return ip in trusted or not trusted

    def _is_rate_limited(self, client_ip: str) -> Tuple[bool, int]:
        now = time.time()
        timestamps = _request_counts[client_ip]
        cutoff = now - self.config.window_seconds
        timestamps = [t for t in timestamps if t > cutoff]
        _request_counts[client_ip] = timestamps

        if len(timestamps) >= self.config.requests_per_window:
            retry_after = int(timestamps[0] + self.config.window_seconds - now)
            return True, max(retry_after, 1)
        _request_counts[client_ip].append(now)
        remaining = self.config.requests_per_window - len(timestamps) - 1
        return False, remaining

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
