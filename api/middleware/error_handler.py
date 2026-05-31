"""Error handler middleware for structured error responses."""

from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

from ..models.errors import APIError, ErrorResponse

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware to handle exceptions and return structured error responses."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            return await self.handle_exception(request, exc)

    async def handle_exception(self, request: Request, exc: Exception) -> JSONResponse:
        """Convert exceptions to structured error responses."""
        request_id = getattr(request.state, "request_id", None)

        # Handle custom APIError exceptions
        if isinstance(exc, APIError):
            return JSONResponse(
                status_code=exc.status_code,
                content=ErrorResponse(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                    request_id=request_id,
                ).model_dump(exclude_none=True),
            )

        # Handle FastAPI validation errors
        if isinstance(exc, RequestValidationError):
            details = {
                "validation_errors": [
                    {
                        "field": ".".join(str(loc) for loc in err["loc"]),
                        "message": err["msg"],
                        "type": err["type"],
                    }
                    for err in exc.errors()
                ]
            }
            return JSONResponse(
                status_code=422,
                content=ErrorResponse(
                    code="VALIDATION_ERROR",
                    message="Request validation failed",
                    details=details,
                    request_id=request_id,
                ).model_dump(exclude_none=True),
            )

        # Handle FastAPI HTTPException
        if isinstance(exc, (HTTPException, StarletteHTTPException)):
            code = self._status_to_code(exc.status_code)
            return JSONResponse(
                status_code=exc.status_code,
                content=ErrorResponse(
                    code=code,
                    message=str(exc.detail),
                    request_id=request_id,
                ).model_dump(exclude_none=True),
            )

        # Handle unexpected exceptions
        logger.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred",
                request_id=request_id,
            ).model_dump(exclude_none=True),
        )

    def _status_to_code(self, status_code: int) -> str:
        """Map HTTP status codes to error codes."""
        mapping = {
            400: "BAD_REQUEST",
            401: "AUTH_FAILED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            500: "INTERNAL_ERROR",
            503: "SERVICE_UNAVAILABLE",
        }
        return mapping.get(status_code, "UNKNOWN_ERROR")
