"""Request ID middleware for log correlation and distributed tracing."""
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("openagents")

class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Accept client-provided X-Request-ID for distributed tracing, else generate UUID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Attach to request state for downstream access
        request.state.request_id = request_id
        
        # Configure logger context for this request (using a custom log filter or extra)
        # For simplicity in this demo, we'll just pass it through headers
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        
        # Log the request completion with ID
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} - {response.status_code}"
        )
        
        return response
