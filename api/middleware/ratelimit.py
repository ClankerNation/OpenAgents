"""Rate limiting middleware for the OpenAgents API."""
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from api.middleware.auth import decode_token
from jwt import ExpiredSignatureError, InvalidTokenError

# Rate limits
AUTH_LIMIT = 1000      # authenticated users per minute
ANON_LIMIT = 100       # anonymous users per minute
WINDOW_SIZE = 60       # 60 seconds window

# In-memory storage for request counts
# In production, use Redis or similar
_request_counts = {
    "auth": {},   # key -> (count, window_start)
    "anon": {}    # key -> (count, window_start)
}


def _get_key(request: Request) -> str:
    """Extract identifier for rate limiting."""
    # Check for Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove 'Bearer '
        try:
            payload = decode_token(token)
            # Use user id if available, otherwise fall back to IP
            user_id = payload.get("sub")
            if user_id:
                return f"auth:{user_id}"
        except (ExpiredSignatureError, InvalidTokenError):
            pass  # fall back to IP
    # Fallback to IP address
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"anon:{ip}"


def _is_authenticated(request: Request) -> bool:
    """Check if request has a valid authentication token."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:]
    try:
        decode_token(token)
        return True
    except (ExpiredSignatureError, InvalidTokenError):
        return False


class RateLimiter(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health check
        if request.url.path == "/health":
            return await call_next(request)

        key = _get_key(request)
        is_auth = _is_authenticated(request)
        limit = AUTH_LIMIT if is_auth else ANON_LIMIT

        now = time.time()
        window_start = now - (now % WINDOW_SIZE)

        # Get current count and window start for this key
        count_dict = _request_counts["auth" if is_auth else "anon"]
        count, start = count_dict.get(key, (0, window_start))

        # Reset if we're in a new window
        if start != window_start:
            count = 0
            start = window_start

        # Increment count
        count += 1
        count_dict[key] = (count, start)

        # If over limit, return 429
        if count > limit:
            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={
                    "Retry-After": str(WINDOW_SIZE),
                },
            )

        # Process request
        response: Response = await call_next(request)

        # Add rate limit headers
        remaining = max(0, limit - count)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(start + WINDOW_SIZE))

        return response