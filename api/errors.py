"""
Structured error handling for the OpenAgents API.

@fix-author OWL (Bounty Brain agent)
@date 2026-06-16
@runtime OS=Linux 6.8.0-124-generic, arch=x86_64, workdir=/tmp/OpenAgents, shell=/bin/bash
"""

import uuid
from typing import Any, Dict, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware


# Error codes
ERROR_CODES: Dict[str, Dict[str, Any]] = {
    "VALIDATION_ERROR": {"status": 400, "message": "Request validation failed"},
    "NOT_FOUND": {"status": 404, "message": "Resource not found"},
    "AUTH_FAILED": {"status": 401, "message": "Authentication failed"},
    "FORBIDDEN": {"status": 403, "message": "Access denied"},
    "RATE_LIMITED": {"status": 429, "message": "Rate limit exceeded"},
    "INTERNAL_ERROR": {"status": 500, "message": "Internal server error"},
}


class APIError(Exception):
    """Base API error with structured response."""

    def __init__(self, code: str, message: str = "", details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message or ERROR_CODES.get(code, {}).get("message", "Unknown error")
        self.details: Dict[str, Any] = details if details is not None else {}
        self.status: int = ERROR_CODES.get(code, {}).get("status", 500)
        super().__init__(self.message)


class NotFoundError(APIError):
    def __init__(self, resource: str = "Resource", resource_id: Any = None):
        details: Dict[str, Any] = {"resource": resource}
        if resource_id is not None:
            details["id"] = str(resource_id)
        super().__init__("NOT_FOUND", f"{resource} not found", details)


class AuthError(APIError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__("AUTH_FAILED", message)


class ForbiddenError(APIError):
    def __init__(self, message: str = "Access denied"):
        super().__init__("FORBIDDEN", message)


class ValidationError(APIError):
    def __init__(self, details: Optional[Dict[str, Any]] = None):
        super().__init__("VALIDATION_ERROR", "Request validation failed", details)


def create_error_response(code: str, message: str, status: int,
                          details: Optional[Dict[str, Any]] = None,
                          request_id: Optional[str] = None) -> JSONResponse:
    """Create a standardized error response."""
    body: Dict[str, Any] = {
        "code": code,
        "message": message,
        "details": details if details is not None else {},
    }
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=status, content=body)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle custom APIError exceptions."""
    request_id = getattr(request.state, "request_id", None)
    return create_error_response(
        code=exc.code,
        message=exc.message,
        status=exc.status,
        details=exc.details,
        request_id=request_id if request_id else None,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI validation errors with field-level details."""
    request_id = getattr(request.state, "request_id", None)
    # Extract field-level error details
    field_errors: Dict[str, list] = {}
    for error in exc.errors():
        loc = error.get("loc", [])
        # Skip the first element if it's 'body' or 'query'
        field_path = ".".join(str(l) for l in loc[1:]) if len(loc) > 1 else str(loc[0]) if loc else "unknown"
        if field_path not in field_errors:
            field_errors[field_path] = []
        field_errors[field_path].append(error.get("msg", "Invalid value"))

    return create_error_response(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        status=400,
        details={"fields": field_errors},
        request_id=request_id if request_id else None,
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors — never leak internals."""
    request_id = getattr(request.state, "request_id", None)
    return create_error_response(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        status=500,
        details={},
        request_id=request_id if request_id else None,
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request for log correlation."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        # Use client-provided request ID or generate one
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
