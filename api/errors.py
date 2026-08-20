# @fix-author rafaio1
# @date 2026-08-20T00:00:00Z
# @runtime linux x64 /tmp/OpenAgents bash
# @platform-config Agentic bounty-hunter workflow

"""Structured error responses for the OpenAgents API."""

import uuid
from typing import Any, Dict, Optional
from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorCode:
    """Standard error codes for consistent API responses."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    FORBIDDEN = "FORBIDDEN"


class StructuredError(Exception):
    """Base exception for structured API errors."""

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


class ValidationError(StructuredError):
    def __init__(self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            status_code=422,
            details=details or {},
        )


class NotFoundError(StructuredError):
    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=message,
            status_code=404,
            details=details or {},
        )


class AuthFailedError(StructuredError):
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.AUTH_FAILED,
            message=message,
            status_code=401,
            details=details or {},
        )


class RateLimitedError(StructuredError):
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=message,
            status_code=429,
            details=details or {},
        )


class InternalError(StructuredError):
    def __init__(self, message: str = "Internal server error", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            message=message,
            status_code=500,
            details=details or {},
        )


def get_request_id(request: Request) -> str:
    """Extract or generate a request ID for tracing."""
    return request.headers.get("X-Request-ID", str(uuid.uuid4()))


async def structured_error_handler(request: Request, exc: StructuredError) -> JSONResponse:
    """Handle StructuredError exceptions with consistent format."""
    request_id = get_request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert standard HTTPException to structured format."""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        request_id = get_request_id(request)
        # Map status codes to error codes
        code_map = {
            400: ErrorCode.BAD_REQUEST,
            401: ErrorCode.AUTH_FAILED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            422: ErrorCode.VALIDATION_ERROR,
            429: ErrorCode.RATE_LIMITED,
        }
        code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": code,
                "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "details": {},
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    # Fallback for unexpected exceptions
    request_id = get_request_id(request)
    return JSONResponse(
        status_code=500,
        content={
            "code": ErrorCode.INTERNAL_ERROR,
            "message": "An unexpected error occurred",
            "details": {},
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert Pydantic validation errors to structured format with field details."""
    from pydantic import ValidationError as PydanticValidationError

    request_id = get_request_id(request)
    field_errors = {}

    if isinstance(exc, PydanticValidationError):
        for error in exc.errors():
            loc = ".".join(str(l) for l in error.get("loc", []))
            field_errors[loc] = error.get("msg", "Invalid value")

    return JSONResponse(
        status_code=422,
        content={
            "code": ErrorCode.VALIDATION_ERROR,
            "message": "Request validation failed",
            "details": {"fields": field_errors},
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )
