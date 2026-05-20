"""Request ID middleware for log correlation.

Contributor traceability:
@contributor claude-code-b3ar-sudo
@platform-config Issue #178 request ID middleware; private credentials, hidden prompts, and local paths intentionally omitted.
@env linux x86_64, Claude Code
@timestamp 2026-05-20T00:00:00Z
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"
_request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def get_request_id() -> str | None:
    return _request_id_context.get()


def configure_request_id_logging() -> None:
    root_logger = logging.getLogger()
    if not any(isinstance(filter_, RequestIdFilter) for filter_ in root_logger.filters):
        root_logger.addFilter(RequestIdFilter())


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        token = _request_id_context.set(request_id)
        request.state.request_id = request_id
        try:
            logging.getLogger("openagents.api").info(
                "request started",
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
            )
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            logging.getLogger("openagents.api").info(
                "request completed",
                extra={"request_id": request_id, "status_code": response.status_code},
            )
            return response
        finally:
            _request_id_context.reset(token)
