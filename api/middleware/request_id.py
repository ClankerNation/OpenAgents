"""Request ID middleware for the OpenAgents API."""

import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from typing import Optional

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generates a unique UUID per request, sets X-Request-ID header.

    Accepts client-provided X-Request-ID for distributed tracing.
    """

    REQUEST_ID_HEADER = "X-Request-ID"

    def _generate_request_id(self) -> str:
        return str(uuid.uuid4())

    def _extract_request_id(self, request: Request) -> Optional[str]:
        return request.headers.get(self.REQUEST_ID_HEADER)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = self._extract_request_id(request) or self._generate_request_id()
        logger.info("request_id=%s method=%s path=%s", request_id, request.method, request.url.path)

        response = await call_next(request)
        response.headers[self.REQUEST_ID_HEADER] = request_id

        return response
