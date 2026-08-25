# @fix-author rafaio1
# @date 2026-08-25T05:30:00Z
# @runtime linux x64 /tmp/openagents_issue_202 bash
# @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for structured error responses (Issue #202)
"""Structured error response schema and exception handlers for the OpenAgents API.

Implements consistent error format with error codes, field-level validation
details, and request ID correlation per Issue #202 requirements.

Closes #202
"""

import uuid
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError


class ErrorCode:
    """Standardized error codes for API responses."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"


class ApiError(Exception):
    """Base exception for structured API errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(ApiError):
    """Resource not found error."""
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            status_code=404,
            details={"resource": resource, "identifier": str(identifier)},
        )


class AuthenticationError(ApiError):
    """Authentication or authorization failure."""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            code=ErrorCode.AUTH_FAILED,
            message=message,
            status_code=401,
        )


class ForbiddenError(ApiError):
    """Access denied."""
    def __init__(self, message: str = "Access denied"):
        super().__init__(
            code=ErrorCode.FORBIDDEN,
            message=message,
            status_code=403,
        )


class RateLimitError(ApiError):
    """Rate limit exceeded."""
    def __init__(self, retry_after: int, tier: str = "anonymous"):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message="Rate limit exceeded",
            status_code=429,
            details={"retry_after_seconds": retry_after, "tier": tier},
        )


def build_error_response(
    request: Request,
    code: str,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Build a standardized error JSON response with request ID."""
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    body: Dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details:
        body["details"] = details

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers={"X-Request-ID": request_id},
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Handle custom ApiError exceptions."""
    return build_error_response(
        request,
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )


async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Convert Pydantic validation errors to structured format with field details."""
    field_errors = []
    for error in exc.errors():
        field_path = ".".join(str(loc) for loc in error.get("loc", []) if loc != "body")
        field_errors.append({
            "field": field_path or "_root",
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        })

    return build_error_response(
        request,
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        status_code=422,
        details={"fields": field_errors},
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions — returns 500 without leaking internals."""
    import logging
    logger = logging.getLogger(__name__)
    logger.exception("Unhandled exception: %s", exc)

    return build_error_response(
        request,
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal server error occurred",
        status_code=500,
    )
