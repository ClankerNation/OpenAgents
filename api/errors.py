"""
@fix-author
  name: Hermes Agent (simisdav55-oss)
  date: 2026-05-27
  runtime:
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/shenhua/OpenAgents
    shell: bash
  initialization_payload: |
    You are Hermes Agent, an intelligent AI assistant.
    Task: add structured error responses with error codes to OpenAgents API.
    Define error schema, codes, handlers, request ID middleware, tests.
"""

"""
Structured error responses for OpenAgents API.

Provides consistent error schema, error codes, and exception handlers
for all API endpoints.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Any, Optional
import uuid
import time


# ── Error Codes ──────────────────────────────────────────────────────

class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"


# ── Error Schema ─────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    field: Optional[str] = None
    issue: Optional[str] = None


class ErrorResponse(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[list[ErrorDetail] | dict[str, Any]] = Field(
        default=None, description="Additional error context"
    )
    request_id: Optional[str] = Field(default=None, description="Unique request identifier")


# ── Custom Exception ─────────────────────────────────────────────────

class APIError(Exception):
    """Base exception for API errors with structured error response."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[list[ErrorDetail] | dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found", details: Any = None):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class AuthError(APIError):
    def __init__(self, message: str = "Authentication failed", details: Any = None):
        super().__init__(
            code=ErrorCode.AUTH_FAILED,
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class RateLimitError(APIError):
    def __init__(self, message: str = "Rate limit exceeded", details: Any = None):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class ValidationError(APIError):
    def __init__(self, message: str = "Validation failed", details: Any = None):
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


# ── Request ID Middleware ────────────────────────────────────────────

async def request_id_middleware(request: Request, call_next):
    """Adds a unique request_id to each request."""
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start_time = time.time()

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(int((time.time() - start_time) * 1000))
    return response


# ── Exception Handlers ───────────────────────────────────────────────

def _make_error_response(
    code: str,
    message: str,
    request_id: Optional[str] = None,
    details: Any = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> JSONResponse:
    """Build a structured JSON error response."""
    body: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details:
        body["details"] = details
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=body)


async def api_error_handler(request: Request, exc: APIError):
    """Handler for custom APIError exceptions."""
    request_id = getattr(request.state, "request_id", None)
    return _make_error_response(
        code=exc.code,
        message=exc.message,
        request_id=request_id,
        details=exc.details,
        status_code=exc.status_code,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Handler for FastAPI request validation errors."""
    request_id = getattr(request.state, "request_id", None)
    field_errors = []
    for err in exc.errors():
        field_errors.append(
            ErrorDetail(
                field=".".join(str(loc) for loc in err.get("loc", [])),
                issue=err.get("msg", str(err)),
            )
        )
    return _make_error_response(
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        request_id=request_id,
        details=[e.model_dump() for e in field_errors],
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def http_error_handler(request: Request, exc: Exception):
    """Generic fallback for unhandled HTTPExceptions."""
    request_id = getattr(request.state, "request_id", None)
    status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    detail = getattr(exc, "detail", str(exc))

    # Map status codes to error codes
    code_map = {
        status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
        status.HTTP_401_UNAUTHORIZED: ErrorCode.AUTH_FAILED,
        status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
        status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
        status.HTTP_422_UNPROCESSABLE_ENTITY: ErrorCode.VALIDATION_ERROR,
        status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    }
    code = code_map.get(status_code, ErrorCode.INTERNAL_ERROR)

    return _make_error_response(
        code=code,
        message=str(detail),
        request_id=request_id,
        status_code=status_code,
    )


async def unhandled_error_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions (500)."""
    request_id = getattr(request.state, "request_id", None)
    return _make_error_response(
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal server error occurred",
        request_id=request_id,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ── Setup ────────────────────────────────────────────────────────────

def setup_error_handling(app):
    """Register all error handlers and middleware on the FastAPI app."""
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    # Keep HTTPException handler for backwards compat
    from fastapi import HTTPException
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
