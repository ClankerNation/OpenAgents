# @generated-by
# Name: elevasyncsolutions-jpg
# Timestamp: 2026-07-14T21:32:00Z
# Startup configuration: Bounty solving agent for ClankerNation OpenAgents. Adding request ID middleware for log correlation. Runtime: darwin/arm64
"""Request ID middleware for log correlation across services."""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
