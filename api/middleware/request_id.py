import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-ID"
LOG_FORMAT = "%(asctime)s [%(request_id)s] %(levelname)s %(name)s: %(message)s"


class RequestIDLogFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.request_id = ""

    def filter(self, record):
        record.request_id = self.request_id or "-"
        return True


_request_id_filter = RequestIDLogFilter()


def setup_request_id_logging():
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(_request_id_filter)
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler.addFilter(_request_id_filter)
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)


def get_request_id() -> str:
    return _request_id_filter.request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        _request_id_filter.request_id = request_id

        response: Response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
