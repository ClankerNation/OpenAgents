"""Request ID middleware and logging helpers for API trace correlation."""

import logging
import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


REQUEST_ID_HEADER = "X-Request-ID"
_request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("openagents.request_id")


def get_request_id() -> str:
    """Return the request ID currently bound to this async context."""

    return _request_id_context.get()


class RequestIdLogFilter(logging.Filter):
    """Attach the active request ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


def install_request_id_log_filter() -> None:
    """Install the request ID log filter on API loggers once."""

    for logger_name in ("openagents", "uvicorn", "uvicorn.access", "uvicorn.error"):
        target = logging.getLogger(logger_name)
        if not any(isinstance(existing, RequestIdLogFilter) for existing in target.filters):
            target.addFilter(RequestIdLogFilter())


def _client_request_id(request: Request) -> str:
    header_value = request.headers.get(REQUEST_ID_HEADER)
    if header_value and "\r" not in header_value and "\n" not in header_value:
        return header_value
    return str(uuid.uuid4())


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Preserve or generate request IDs and expose them in responses/logs."""

    async def dispatch(self, request: Request, call_next):
        request_id = _client_request_id(request)
        token = _request_id_context.set(request_id)

        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                },
            )
            return response
        finally:
            _request_id_context.reset(token)
