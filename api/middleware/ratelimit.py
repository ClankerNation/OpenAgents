
import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Tiered Rate Limiting Logic
        auth_state = request.state.auth if hasattr(request.state, 'auth') else None
        
        limit = 60 # Anonymous default
        tier = "anonymous"
        
        if auth_state:
            if auth_state.get("is_premium"):
                limit = 1000
                tier = "premium"
            else:
                limit = 300
                tier = "authenticated"
        
        # Simple local rate limiting for demonstration
        # In a real fix, this would use Redis or a DB
        # ... logic to check and increment counter ...
        
        response = await call_next(request)
        
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Tier"] = tier
        
        return response
