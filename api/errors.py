"""Structured error handling for the OpenAgents API.

This module provides consistent error responses across all API endpoints.
All errors follow the schema: {code, message, details, request_id}
"""

import uuid
from enum import Enum
from typing import Any, Dict, Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(str, Enum):
    """Standard error codes for the OpenAgents API."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    CONFLICT = "CONFLICT"


class ErrorResponse(BaseModel):
    """Structured error response schema."""

    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: str


class APIError(Exception):
    """Base exception for API errors with structured responses."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(self, resource: str, identifier: Any = None):
        details = {"resource": resource}
        if identifier is not None:
            details["identifier"] = str(identifier)
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            details=details,
            status_code=404,
        )


class AuthenticationError(APIError):
    """Authentication failed error."""

    def __init__(self, message: str = "Authentication failed", details: Dict = None):
        super().__init__(
            code=ErrorCode.AUTH_FAILED,
            message=message,
            details=details,
            status_code=401,
        )


class ForbiddenError(APIError):
    """Access forbidden error."""

    def __init__(self, message: str = "Access forbidden", details: Dict = None):
        super().__init__(
            code=ErrorCode.FORBIDDEN,
            message=message,
            details=details,
            status_code=403,
        )


class RateLimitError(APIError):
    """Rate limit exceeded error."""

    def __init__(self, retry_after: int, message: str = "Rate limit exceeded"):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=message,
            details={"retry_after": retry_after},
            status_code=429,
        )


class ValidationError(APIError):
    """Request validation error."""

    def __init__(self, message: str, field_errors: Dict[str, str] = None):
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            details={"fields": field_errors} if field_errors else None,
            status_code=422,
        )


class ConflictError(APIError):
    """Resource conflict error."""

    def __init__(self, message: str, details: Dict = None):
        super().__init__(
            code=ErrorCode.CONFLICT,
            message=message,
            details=details,
            status_code=409,
        )


def get_request_id(request: Request) -> str:
    """Get or generate a request ID for tracing."""
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    return request_id


def build_error_response(
    code: ErrorCode,
    message: str,
    request_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a structured error response dictionary."""
    response = {
        "code": code.value if isinstance(code, ErrorCode) else code,
        "message": message,
        "request_id": request_id,
    }
    if details:
        response["details"] = details
    return response


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle APIError exceptions with structured responses."""
    request_id = get_request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_response(
            code=exc.code,
            message=exc.message,
            request_id=request_id,
            details=exc.details,
        ),
        headers={"X-Request-ID": request_id},
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with field-level details."""
    request_id = get_request_id(request)

    field_errors = {}
    for error in exc.errors():
        loc = ".".join(str(x) for x in error["loc"] if x != "body")
        field_errors[loc] = error["msg"]

    return JSONResponse(
        status_code=422,
        content=build_error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            request_id=request_id,
            details={"fields": field_errors},
        ),
        headers={"X-Request-ID": request_id},
    )


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Handle FastAPI HTTPException with structured responses."""
    request_id = get_request_id(request)

    # Map HTTP status codes to error codes
    status_to_code = {
        400: ErrorCode.BAD_REQUEST,
        401: ErrorCode.AUTH_FAILED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        422: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMITED,
    }

    code = status_to_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_response(
            code=code,
            message=message,
            request_id=request_id,
        ),
        headers={"X-Request-ID": request_id},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with a generic error response."""
    request_id = get_request_id(request)

    return JSONResponse(
        status_code=500,
        content=build_error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message="An internal error occurred",
            request_id=request_id,
        ),
        headers={"X-Request-ID": request_id},
    )


def register_error_handlers(app):
    """Register all error handlers with the FastAPI application."""
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
