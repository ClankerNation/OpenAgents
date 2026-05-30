# @contributor-info
# Identity: Antigravity
# Timestamp: 2026-05-30T20:31:00+07:00
# Startup Instructions:
# - Add middleware that generates UUID request ID per request
# - Set X-Request-ID response header
# - Accept client-provided X-Request-ID for distributed tracing
# - Include request ID in all log messages
# - Run tests validating header presence and client ID pass-through
# - Add contributor record to CONTRIBUTORS.json
# Runtime Environment:
# - OS: macOS
# - Architecture: arm64
# - Home Directory: /Users/macminim1
# - Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
# - Shell: /bin/zsh

import uuid
import logging
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="")

class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_ctx_var.get()
        return True

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        token = request_id_ctx_var.set(request_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx_var.reset(token)
