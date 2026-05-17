"""
Request ID middleware for the OpenAgents API.

Generates a UUID per request for log correlation, sets the X-Request-ID
response header, and accepts client-provided request IDs for distributed
tracing compatibility.
"""

import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("openagents.request_id")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that ensures every request has a unique request ID.

    - Accepts client-provided X-Request-ID header for distributed tracing
    - Generates a UUID v4 if none provided
    - Sets X-Request-ID on the response
    - Injects request_id into request.state for downstream handlers
    """

    async def dispatch(self, request: Request, call_next):
        # Accept client-provided request ID for distributed tracing, or generate one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Make request_id available to downstream handlers via request.state
        request.state.request_id = request_id

        # Log the incoming request with its ID
        logger.info(
            "Request started",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )

        # Process the request
        response: Response = await call_next(request)

        # Set the response header so clients can correlate
        response.headers["X-Request-ID"] = request_id

        return response
