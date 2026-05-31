"""Custom exception handlers for structured error responses.

Converts all exceptions (HTTPException, RequestValidationError, generic)
into the canonical ErrorResponse format with consistent error codes.
"""

import uuid
import traceback
from typing import Union
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from api.models.errors import ErrorResponse, ErrorCode, HTTP_STATUS_TO_CODE


def generate_request_id() -> str:
    """Generate a unique request identifier."""
    return str(uuid.uuid4())


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that adds a unique request_id to each request."""

    async def dispatch(self, request: Request, call_next):
        request_id = generate_request_id()
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def get_request_id(request: Request) -> str:
    """Extract request_id from request state, or generate one if missing."""
    return getattr(request.state, "request_id", generate_request_id())


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException with structured error response."""
    request_id = get_request_id(request)

    # Map HTTP status to error code
    error_code = HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    error_response = ErrorResponse(
        code=error_code,
        message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        details={},
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle validation errors with field-level details."""
    request_id = get_request_id(request)

    # Extract field-level validation errors
    field_errors = []
    for error in exc.errors():
        field_path = ".".join(str(loc) for loc in error["loc"])
        field_errors.append({
            "field": field_path,
            "message": error["msg"],
            "type": error["type"],
        })

    error_response = ErrorResponse(
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details={"fields": field_errors},
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with structured error response."""
    request_id = get_request_id(request)

    # Log the full traceback for debugging (in production, send to logging service)
    error_trace = traceback.format_exc()
    print(f"[ERROR] Request {request_id}: {error_trace}")

    error_response = ErrorResponse(
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal error occurred",
        details={"type": type(exc).__name__},
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
    )
