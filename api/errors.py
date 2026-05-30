"""
@fix-author
  name       : Hermes Agent (kejuunuy)
  date       : 2026-05-30
  environment: Python 3.11, FastAPI 0.133.1, Pydantic 2.13.4
  issue      : #202 — Implement structured error responses
  bounty     : $8600

Structured error responses for the OpenAgents API.

Defines a consistent error schema, custom exception classes, request-ID
middleware, and global exception handlers so that **every** error returned
by the API follows the shape:

    {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Human-readable description",
            "details": { ... },
            "request_id": "a1b2c3d4"
        }
    }
"""

from __future__ import annotations

import enum
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

class ErrorCode(str, enum.Enum):
    """Canonical error codes returned by the API.

    | Code              | HTTP | Meaning                                        |
    |-------------------|------|-------------------------------------------------|
    | VALIDATION_ERROR  | 422  | Request body / params failed validation         |
    | NOT_FOUND         | 404  | Requested resource does not exist               |
    | AUTH_FAILED       | 401  | Authentication token missing / invalid / expired|
    | FORBIDDEN         | 403  | Authenticated but not authorized                |
    | RATE_LIMITED      | 429  | Too many requests in the current window         |
    | CONFLICT          | 409  | State conflict (e.g. duplicate escrow)           |
    | BAD_REQUEST       | 400  | Generic client error (invalid state transition) |
    | INTERNAL_ERROR    | 500  | Unexpected server-side failure                  |
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Map ErrorCode -> default HTTP status code
_CODE_TO_STATUS: Dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.AUTH_FAILED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.CONFLICT: 409,
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.INTERNAL_ERROR: 500,
}


# ---------------------------------------------------------------------------
# Error response schema (Pydantic model)
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    """The inner ``error`` object in every error response."""

    code: str
    message: str
    details: Dict[str, Any] = {}
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Top-level error envelope."""

    error: ErrorDetail


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class APIError(Exception):
    """Raise this anywhere in route / middleware code to produce a structured
    error response.

    Parameters
    ----------
    code : ErrorCode
        One of the canonical error codes.
    message : str
        Human-readable message (safe to show clients).
    details : dict, optional
        Arbitrary key-value context (e.g. ``{"field": "name", "reason": "…"}``).
    status_code : int, optional
        Override the default HTTP status for *code*.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: Optional[int] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code or _CODE_TO_STATUS.get(code, 500)
        super().__init__(message)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_error_response(
    *,
    code: str,
    message: str,
    details: Dict[str, Any] | None = None,
    request_id: str | None = None,
    status_code: int = 500,
) -> JSONResponse:
    """Construct a JSONResponse with the canonical error envelope."""
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or {},
            request_id=request_id,
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

async def _api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return _build_error_response(
        code=exc.code.value,
        message=exc.message,
        details=exc.details,
        request_id=getattr(request.state, "request_id", None),
        status_code=exc.status_code,
    )


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Catch unhandled ``HTTPException`` from FastAPI / Starlette and wrap
    them in the structured envelope so the schema is never violated.

    Maps common status codes to canonical error codes.
    """
    _status_to_code = {
        400: ErrorCode.BAD_REQUEST,
        401: ErrorCode.AUTH_FAILED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        422: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMITED,
    }
    code = _status_to_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return _build_error_response(
        code=code.value,
        message=message,
        details={},
        request_id=getattr(request.state, "request_id", None),
        status_code=exc.status_code,
    )


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Turn Pydantic / FastAPI validation errors into structured responses
    with field-level ``details``.
    """
    field_errors: Dict[str, Any] = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        # loc is a tuple like ("body", "name") – join to dotted path
        field = ".".join(str(p) for p in loc)
        field_errors[field] = err.get("msg", "Invalid value")
    return _build_error_response(
        code=ErrorCode.VALIDATION_ERROR.value,
        message="Request validation failed",
        details={"fields": field_errors},
        request_id=getattr(request.state, "request_id", None),
        status_code=422,
    )


async def _generic_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Last-resort handler for any unhandled exception. Returns 500 with
    a safe message (no stack traces leaked to clients).
    """
    return _build_error_response(
        code=ErrorCode.INTERNAL_ERROR.value,
        message="An unexpected error occurred. Please try again later.",
        details={},
        request_id=getattr(request.state, "request_id", None),
        status_code=500,
    )


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a unique ``X-Request-ID`` to every request and echoes it
    back on the response.  The ID is stored on ``request.state.request_id``
    so exception handlers can include it in error responses.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_error_handlers(app: FastAPI) -> None:
    """Wire up all exception handlers on *app*.

    Note: RequestIDMiddleware is added separately in main.py so that its
    position in the middleware stack can be controlled (it must be outermost).
    """
    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    # Generic catch-all must be registered last
    app.add_exception_handler(Exception, _generic_error_handler)
