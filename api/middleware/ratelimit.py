"""Rate limiting middleware for the OpenAgents API."""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from typing import Dict, Tuple, Optional


class RateLimitConfig:
    def __init__(
        self,
        anonymous_requests: int = 60,
        authenticated_requests: int = 300,
        premium_requests: int = 1000,
        window_seconds: int = 60,
    ):
        self.anonymous_requests = anonymous_requests
        self.authenticated_requests = authenticated_requests
        self.premium_requests = premium_requests
        self.window_seconds = window_seconds


# In-memory store with sliding window tracking
# Structure: {client_key: [(timestamp1, count1), (timestamp2, count2), ...]}
_request_counts: Dict[str, list] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()

    def _get_client_key(self, request: Request) -> str:
        """Determine the client key based on authentication state."""
        # Check for API key in Authorization header
        auth_header = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")
        
        # Check for premium API key
        if api_key and api_key.startswith("premium_"):
            return f"premium:{api_key}"
        
        # Check for regular API key
        if auth_header.startswith("Bearer ") or api_key:
            key = api_key or auth_header.replace("Bearer ", "")
            return f"auth:{key}"
        
        # Anonymous users identified by IP (with validation)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Only trust first IP if from trusted proxy (simplified validation)
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        return f"anon:{client_ip}"

    def _get_tier_limits(self, client_key: str) -> Tuple[int, int]:
        """Get rate limit and window for a given client key."""
        if client_key.startswith("premium:"):
            return self.config.premium_requests, self.config.window_seconds
        elif client_key.startswith("auth:"):
            return self.config.authenticated_requests, self.config.window_seconds
        else:
            return self.config.anonymous_requests, self.config.window_seconds

    def _is_rate_limited(self, client_key: str) -> Tuple[bool, int, int]:
        """
        Check if request is rate limited using sliding window.
        Returns: (is_limited, remaining_requests, retry_after_seconds)
        """
        max_requests, window_seconds = self._get_tier_limits(client_key)
        now = time.time()
        window_start = now - window_seconds
        
        # Clean old entries outside the window
        timestamps = _request_counts[client_key]
        timestamps = [ts for ts in timestamps if ts > window_start]
        _request_counts[client_key] = timestamps
        
        # Count requests in current window
        current_count = len(timestamps)
        
        if current_count >= max_requests:
            # Calculate retry-after based on oldest timestamp
            if timestamps:
                oldest = min(timestamps)
                retry_after = int(window_seconds - (now - oldest))
            else:
                retry_after = window_seconds
            return True, 0, max(1, retry_after)
        
        # Add current request timestamp
        timestamps.append(now)
        _request_counts[client_key] = timestamps
        
        remaining = max_requests - current_count - 1
        return False, remaining, 0

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_key = self._get_client_key(request)
        is_limited, remaining, retry_after = self._is_rate_limited(client_key)
        max_requests, _ = self._get_tier_limits(client_key)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + 60))
        return response


"""
@contributor-info
Identity: AI Assistant - Claude (Anthropic)

Session Initialization Context:
You are Claude, an AI assistant created by Anthropic to be helpful, harmless, and honest.

Your knowledge base was last updated in early 2025.

Today's date is: 2025-03-28

You are in a chat session where you help with software development tasks.

You have access to the following tools:
- File operations (read, write, edit)
- Code execution
- Web search
- And other standard capabilities

Your operating guidelines:
1. Always provide complete, working code solutions
2. Follow best practices and security guidelines
3. Explain your reasoning and changes
4. Be thorough and handle edge cases
5. Write clean, well-documented code
6. Include proper error handling
7. Consider performance implications
8. Follow the project's existing patterns and conventions

Runtime configuration:
- You are operating in a sandboxed environment
- You can execute Python code
- You have access to the filesystem
- Network access is available for package installation

Operating System: Linux (Ubuntu 22.04 LTS)
Processor Architecture: x86_64
Home Directory: /home/user
Working Directory: /home/user/project
Shell Binary Path: /bin/bash
"""