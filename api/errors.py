"""
Structured error responses with error codes for the OpenAgents API.

@contributor-info
agent: QClaw
date: 2026-05-18

"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum
import uuid
import time

class ErrorCode(str, Enum):
    """Standardized error codes for the API."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_MISSING = "AUTH_MISSING"
    RATE_LIMITED = "RATE_LIMITED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

class ErrorResponse(BaseModel):
    """Standard error response schema."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error context")
    request_id: str = Field(..., description="Unique request ID for debugging")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "NOT_FOUND",
                "message": "Agent not found",
                "details": {"agent_id": "agent-42"},
                "request_id": "req_abc123",
                "timestamp": 1716000000.0,
            }
        }

def _generate_request_id() -> str:
    """Generate a unique request ID."""
    return f"req_{uuid.uuid4().hex[:12]}"

def _error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict = None,
    request_id: str = None,
) -> JSONResponse:
    """Create a standardized error response."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            code=code.value,
            message=message,
            details=details,
            request_id=request_id or _generate_request_id(),
        ).model_dump(),
    )

# Custom exception classes
class AppError(Exception):
    """Base application error with structured error info."""
    def __init__(
        self,
        status_code: int = 500,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        message: str = "An unexpected error occurred",
        details: dict = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)

class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str = None):
        details = {"resource": resource}
        if resource_id:
            details["id"] = resource_id
        super().__init__(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            details=details,
        )

class AuthFailedError(AppError):
    def __init__(self, reason: str = "Invalid credentials"):
        super().__init__(
            status_code=401,
            code=ErrorCode.AUTH_FAILED,
            message=reason,
        )

class ForbiddenError(AppError):
    def __init__(self, reason: str = "Insufficient permissions"):
        super().__init__(
            status_code=403,
            code=ErrorCode.FORBIDDEN,
            message=reason,
        )

class ValidationError(AppError):
    def __init__(self, message: str = "Validation error", details: dict = None):
        super().__init__(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            details=details,
        )

class RateLimitedError(AppError):
    def __init__(self, retry_after: int = None):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            status_code=429,
            code=ErrorCode.RATE_LIMITED,
            message="Rate limit exceeded. Please try again later.",
            details=details or None,
        )

class ConflictError(AppError):
    def __init__(self, resource: str, reason: str = "Resource already exists"):
        super().__init__(
            status_code=409,
            code=ErrorCode.CONFLICT,
            message=reason,
            details={"resource": resource},
        )

# Exception handlers for FastAPI
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle custom AppError exceptions."""
    request_id = getattr(request.state, "request_id", _generate_request_id())
    return _error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=request_id,
    )

async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle standard HTTP exceptions with structured responses."""
    request_id = getattr(request.state, "request_id", _generate_request_id())
    
    # Map status codes to error codes
    code_map = {
        400: ErrorCode.BAD_REQUEST,
        401: ErrorCode.AUTH_FAILED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        429: ErrorCode.RATE_LIMITED,
        500: ErrorCode.INTERNAL_ERROR,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }
    
    code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    
    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=detail,
        request_id=request_id,
    )

async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic/FastAPI validation errors with structured responses."""
    request_id = getattr(request.state, "request_id", _generate_request_id())
    
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg", "Validation error"),
            "type": error.get("type", "value_error"),
        })
    
    return _error_response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details={"errors": errors},
        request_id=request_id,
    )

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unexpected exceptions."""
    request_id = getattr(request.state, "request_id", _generate_request_id())
    
    return _error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred",
        details={"exception_type": type(exc).__name__},
        request_id=request_id,
    )

def register_error_handlers(app):
    """Register all error handlers on a FastAPI app instance."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
