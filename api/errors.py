"""Structured error responses for the OpenAgents API.

All API errors follow a consistent schema:
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable description",
        "details": {},        # optional field-level details
        "request_id": "uuid"  # traceability
    }
}

Contributor: iyop666 (https://github.com/iyop666)
"""

import uuid
import traceback
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Map HTTP status codes to error codes
_STATUS_TO_CODE: Dict[int, str] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.AUTH_FAILED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL_ERROR,
}


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    request_id: Optional[str] = None,
) -> JSONResponse:
    """Build a structured error JSON response."""
    body: Dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id or str(uuid.uuid4()),
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

def _get_request_id(request: Request) -> str:
    """Get or generate a request ID."""
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTPException with structured format."""
    code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
        request_id=_get_request_id(request),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with field-level details."""
    details = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err.get("loc", []))
        details.append({
            "field": field,
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })
    return error_response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details=details,
        request_id=_get_request_id(request),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions."""
    return error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal server error occurred",
        request_id=_get_request_id(request),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_error_handlers(app: FastAPI) -> None:
    """Register all structured error handlers on a FastAPI app."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
