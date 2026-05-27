"""Structured error response schema and exception handlers for OpenAgents API.

@fix-author
  name: wanglovefly-oss
  date: 2026-05-27
  @runtime: {os: linux, arch: x64, working_dir: /mnt/c/Users/wsda/OpenAgents, shell: bash}
"""

import uuid
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Error code constants
# ---------------------------------------------------------------------------

class ErrorCode:
    """Standardized error codes for the OpenAgents API."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_CODE_MAP: Dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.AUTH_FAILED,
    status.HTTP_403_FORBIDDEN: ErrorCode.AUTH_FAILED,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_ENTITY: ErrorCode.VALIDATION_ERROR,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorCode.INTERNAL_ERROR,
}


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    """A single field-level validation detail."""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standardized error response body."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Union[List[ErrorDetail], Dict[str, Any]]] = Field(
        default=None, description="Additional error details (e.g. field-level validation errors)"
    )
    request_id: str = Field(..., description="Unique request identifier for traceability")


# ---------------------------------------------------------------------------
# Request ID helpers
# ---------------------------------------------------------------------------

async def _get_request_id(request: Request) -> str:
    """Extract or generate a request_id from the request state/headers."""
    # Prefer middleware-populated request_id
    if hasattr(request.state, "request_id") and request.state.request_id:
        return request.state.request_id
    # Fall back to X-Request-ID header
    req_id = request.headers.get("X-Request-ID")
    if req_id:
        return req_id
    # Last resort — generate one
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

async def _build_error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Optional[Union[List[ErrorDetail], Dict[str, Any]]] = None,
) -> JSONResponse:
    """Build a standardized JSON error response."""
    request_id = await _get_request_id(request)
    body = ErrorResponse(
        code=code,
        message=message,
        details=details,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
    )


async def _map_status_to_code(status_code: int) -> str:
    """Map an HTTP status code to the closest error code."""
    return ERROR_CODE_MAP.get(status_code, ErrorCode.INTERNAL_ERROR)


# ---------------------------------------------------------------------------
# Handler: FastAPI / Pydantic validation errors (422)
# ---------------------------------------------------------------------------

async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle RequestValidationError with field-level details."""
    details: List[ErrorDetail] = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", [])) if error.get("loc") else None
        details.append(
            ErrorDetail(
                field=field or None,
                message=error.get("msg", "Validation error"),
                code=error.get("type"),
            )
        )
    return await _build_error_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details=details,
    )


# ---------------------------------------------------------------------------
# Handler: HTTPException (used throughout routes)
# ---------------------------------------------------------------------------

async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException with standardized format."""
    code = await _map_status_to_code(exc.status_code)
    # If detail is already a dict (structured error), use it
    if isinstance(exc.detail, dict):
        message = exc.detail.get("message", str(exc.detail))
        details = exc.detail.get("details", None)
    else:
        message = str(exc.detail)
        details = None

    return await _build_error_response(
        request=request,
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
    )


# ---------------------------------------------------------------------------
# Handler: Generic / unhandled exceptions (500)
# ---------------------------------------------------------------------------

async def general_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions as INTERNAL_ERROR."""
    return await _build_error_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal server error occurred",
    )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_error_handlers(app: FastAPI) -> None:
    """Register all structured error handlers on a FastAPI application."""
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, general_error_handler)
