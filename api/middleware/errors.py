"""
@contributor: hermes-agent
@platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
@env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
@timestamp: 2026-05-18
"""

"""Structured error response handler for the OpenAgents API.

Defines a consistent error schema, custom exception classes with error codes,
and FastAPI exception handlers that produce structured JSON error responses
including a request_id for traceability.
"""

import uuid
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error schema
# ---------------------------------------------------------------------------

class ErrorResponse:
    """Structured error response matching the required schema:
    {code: string, message: string, details: object, request_id: string}
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.request_id = request_id or str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "request_id": self.request_id,
        }

    def to_json_response(self, status_code: int) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=self.to_dict(),
        )


# ---------------------------------------------------------------------------
# Error code constants
# ---------------------------------------------------------------------------

class ErrorCode:
    """Canonical error codes for all API error responses."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    FORBIDDEN = "FORBIDDEN"
    BAD_REQUEST = "BAD_REQUEST"


# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------

class AppError(Exception):
    """Base application error with structured error code and details."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(code=ErrorCode.NOT_FOUND, message=message, status_code=404, details=details)


class AuthFailedError(AppError):
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(code=ErrorCode.AUTH_FAILED, message=message, status_code=401, details=details)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(code=ErrorCode.FORBIDDEN, message=message, status_code=403, details=details)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation error", details: Optional[Dict[str, Any]] = None):
        super().__init__(code=ErrorCode.VALIDATION_ERROR, message=message, status_code=422, details=details)


class BadRequestError(AppError):
    def __init__(self, message: str = "Bad request", details: Optional[Dict[str, Any]] = None):
        super().__init__(code=ErrorCode.BAD_REQUEST, message=message, status_code=400, details=details)


class RateLimitedError(AppError):
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(code=ErrorCode.RATE_LIMITED, message=message, status_code=429, details=details)


class InternalError(AppError):
    def __init__(self, message: str = "Internal server error", details: Optional[Dict[str, Any]] = None):
        super().__init__(code=ErrorCode.INTERNAL_ERROR, message=message, status_code=500, details=details)


# ---------------------------------------------------------------------------
# Mapping of HTTP status codes to error codes (fallback)
# ---------------------------------------------------------------------------

HTTP_STATUS_TO_ERROR_CODE: Dict[int, str] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.AUTH_FAILED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL_ERROR,
}


# ---------------------------------------------------------------------------
# Request ID generation
# ---------------------------------------------------------------------------

def get_or_generate_request_id(request: Request) -> str:
    """Extract request_id from incoming headers, or generate a new UUID."""
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())


# ---------------------------------------------------------------------------
# FastAPI exception handlers
# ---------------------------------------------------------------------------

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle our custom AppError exceptions."""
    request_id = get_or_generate_request_id(request)
    error = ErrorResponse(
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=request_id,
    )
    logger.error(
        "AppError: code=%s message=%s request_id=%s path=%s",
        exc.code, exc.message, request_id, request.url.path,
    )
    return error.to_json_response(exc.status_code)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle FastAPI/Starlette HTTPException — convert to structured format."""
    request_id = get_or_generate_request_id(request)
    code = HTTP_STATUS_TO_ERROR_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    # Special handling for common status codes
    if exc.status_code == 401:
        code = ErrorCode.AUTH_FAILED
    elif exc.status_code == 403:
        code = ErrorCode.FORBIDDEN
    elif exc.status_code == 404:
        code = ErrorCode.NOT_FOUND
    elif exc.status_code == 429:
        code = ErrorCode.RATE_LIMITED

    # exc.detail can be a string or a dict
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    error = ErrorResponse(
        code=code,
        message=detail,
        details={},
        request_id=request_id,
    )
    logger.warning(
        "HTTPException: status=%d code=%s message=%s request_id=%s path=%s",
        exc.status_code, code, detail, request_id, request.url.path,
    )
    return error.to_json_response(exc.status_code)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic/FastAPI request validation errors."""
    request_id = get_or_generate_request_id(request)

    # Format field-level validation errors
    errors = exc.errors()
    details = {
        "fields": [
            {
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in errors
        ],
    }

    error = ErrorResponse(
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details=details,
        request_id=request_id,
    )
    logger.warning(
        "ValidationError: %d field errors request_id=%s path=%s",
        len(errors), request_id, request.url.path,
    )
    return error.to_json_response(422)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions — returns INTERNAL_ERROR."""
    request_id = get_or_generate_request_id(request)
    error = ErrorResponse(
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred",
        details={},
        request_id=request_id,
    )
    logger.exception(
        "UnhandledException: request_id=%s path=%s",
        request_id, request.url.path,
    )
    return error.to_json_response(500)


# ---------------------------------------------------------------------------
# Registration function
# ---------------------------------------------------------------------------

def register_error_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on a FastAPI application."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)