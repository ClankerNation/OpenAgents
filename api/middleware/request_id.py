"""Request ID middleware for log correlation."""

import uuid
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("openagents")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generates a unique request ID for each request and attaches it to logs."""

    async def dispatch(self, request: Request, call_next):
        # Accept client-provided ID or generate a new one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store on request state for access in handlers
        request.state.request_id = request_id

        # Bind request_id to the logging context
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.request_id = request_id
            return record

        logging.setLogRecordFactory(record_factory)

        try:
            response: Response = await call_next(request)
        finally:
            logging.setLogRecordFactory(old_factory)

        # Set the response header
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request_completed",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )

        return response
