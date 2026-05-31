"""
@fix-author
  name: barnacleagent-svg
  date: 2026-05-31
  platform_init: |
    You are GLM (General Language model), a large language model developed by Z.ai.
    Designed to understand and generate human-like text through training on diverse text data.
    Capabilities include answering questions, providing information, and engaging in conversations.
    Operating as an interactive CLI tool for software engineering tasks.
    Goal: Earn $200 from OSS bounties using barnacleagent-svg GitHub account ONLY.
  runtime:
    os: linux
    arch: x86_64
    working_dir: /home/bennett/projects/OSS-Contributions/OpenAgents/api/middleware
    shell: bash

Three-tier rate limiting middleware for the OpenAgents API.
- 60 req/min for anonymous users
- 300 req/min for authenticated users (JWT)
- 1000 req/min for premium API keys
Uses sliding window algorithm with in-memory storage.
"""

import time
import jwt
import os
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")

ANONYMOUS_LIMIT = 60
AUTHENTICATED_LIMIT = 300
PREMIUM_LIMIT = 1000
WINDOW_SECONDS = 60

class SlidingWindowCounter:
    def __init__(self):
        self.entries: Dict[str, list] = defaultdict(list)

    def prune(self, key: str, now: float):
        cutoff = now - WINDOW_SECONDS
        self.entries[key] = [t for t in self.entries[key] if t > cutoff]

    def count(self, key: str, now: float) -> int:
        self.prune(key, now)
        return len(self.entries[key])

    def increment(self, key: str, now: float):
        self.entries[key].append(now)

_request_log: Dict[str, SlidingWindowCounter] = defaultdict(SlidingWindowCounter)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_auth_type(request: Request) -> Tuple[str, str]:
    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")
    client_ip = _get_client_ip(request)

    if api_key:
        return ("premium", f"apikey:{api_key}")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            sub = payload.get("sub", "unknown")
            roles = payload.get("roles", [])
            if "premium" in roles:
                return ("premium", f"jwt:{sub}")
            return ("authenticated", f"jwt:{sub}")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return ("anonymous", f"ip:{client_ip}")

    return ("anonymous", f"ip:{client_ip}")


def _get_limit(auth_type: str) -> int:
    return {
        "anonymous": ANONYMOUS_LIMIT,
        "authenticated": AUTHENTICATED_LIMIT,
        "premium": PREMIUM_LIMIT,
    }.get(auth_type, ANONYMOUS_LIMIT)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        now = time.time()
        auth_type, key = _get_auth_type(request)
        limit = _get_limit(auth_type)
        counter = _request_log[auth_type]
        current = counter.count(key, now)

        if current >= limit:
            retry_after = int(WINDOW_SECONDS - (now - self._earliest(counter, key, now)))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "auth_type": auth_type,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + retry_after)),
                },
            )

        counter.increment(key, now)
        remaining = limit - current - 1
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(now + WINDOW_SECONDS))
        return response

    def _earliest(self, counter: SlidingWindowCounter, key: str, now: float) -> float:
        entries = counter.entries.get(key, [])
        return entries[0] if entries else now
