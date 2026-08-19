"""
Rate limiting middleware for the OpenAgents API.
@contributor-info ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""

import time
import hashlib
import jwt
import os
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple

from ..models.database import SessionLocal, ApiKey

# Tier limits (requests per minute)
TIER_ANONYMOUS = 60
TIER_AUTHENTICATED = 300
TIER_PREMIUM = 1000

JWT_SECRET = os.environ.get("JWT_SECRET", "default_secret_change_me")
WINDOW_SECONDS = 60

# In-memory store: key -> (count, window_start)
_request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _get_tier_and_key(request: Request) -> Tuple[int, str]:
    """Determine rate limit tier and a unique key for the client."""
    api_key = request.headers.get("X-API-Key")
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        db = SessionLocal()
        try:
            db_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.revoked == 0).first()
            if db_key:
                # Treat all valid API keys as premium tier for this implementation
                return TIER_PREMIUM, f"apikey:{key_hash}"
        finally:
            db.close()
            
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            user_id = payload.get("sub", "unknown")
            return TIER_AUTHENTICATED, f"jwt:{user_id}"
        except Exception:
            pass
            
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
        
    return TIER_ANONYMOUS, f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        limit, client_key = _get_tier_and_key(request)
        count, window_start = _request_counts[client_key]
        now = time.time()

        if now - window_start >= WINDOW_SECONDS:
            _request_counts[client_key] = (1, now)
            remaining = limit - 1
            reset_time = int(now + WINDOW_SECONDS)
        else:
            if count >= limit:
                retry_after = int(WINDOW_SECONDS - (now - window_start))
                return JSONResponse(
                    status_code=429,
                    content={"error": "Rate limit exceeded", "retry_after": retry_after},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(window_start + WINDOW_SECONDS)),
                    },
                )
            _request_counts[client_key] = (count + 1, window_start)
            remaining = limit - count - 1
            reset_time = int(window_start + WINDOW_SECONDS)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response
