"""
@fix-author
Name: Karry2019web (Hermes Autonomous Agent)
Date: 2026-05-27
Session initialization: This agent is running as a scheduled cron job on Windows 10 (git-bash) via Hermes Agent. 
Model: deepseek-chat via deepseek provider.
Objective: Implement structured error responses with consistent error codes for ClankerNation/OpenAgents API for bounty #202 ($8600).
@runtime
os: Windows 10
arch: x86_64
working_dir: C:\Users\Administrator\AppData\Local\hermes\hermes-agent
shell: git-bash (MSYS)
tools: execute_code (Python via hermes_tools), urllib for GitHub API
---

Structured error responses for OpenAgents API.
Provides consistent error schema {code, message, details, request_id}
across all API endpoints with custom exception classes.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Any, Optional
import uuid
import time


class ErrorCode:
    """Machine-readable error codes for the API."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"


class ErrorDetail(BaseModel):
    """Individual field-level validation error."""
    field: Optional[str] = None
    issue: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standardised error response schema."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[list[ErrorDetail] | dict[str, Any]] = Field(
        default=None, description="Additional error context"
    )
    request_id: Optional[str] = Field(default=None, description="Unique request identifier")


class APIError(Exception):
    """Base exception for API errors with structured response."""
    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST, details: Optional[list[ErrorDetail] | dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found", details: Any = None):
        super().__init__(ErrorCode.NOT_FOUND, message, status.HTTP_404_NOT_FOUND, details)


class AuthError(APIError):
    def __init__(self, message: str = "Authentication failed", details: Any = None):
        super().__init__(ErrorCode.AUTH_FAILED, message, status.HTTP_401_UNAUTHORIZED, details)


class RateLimitError(APIError):
    def __init__(self, message: str = "Rate limit exceeded", details: Any = None):
        super().__init__(ErrorCode.RATE_LIMITED, message, status.HTTP_429_TOO_MANY_REQUESTS, details)


class ValidationError_(APIError):
    def __init__(self, message: str = "Validation error", details: Any = None):
        super().__init__(ErrorCode.VALIDATION_ERROR, message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.code, message=exc.message, details=exc.details,
            request_id=getattr(request.state, "request_id", str(uuid.uuid4())),
        ).model_dump(exclude_none=True),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        ErrorDetail(field=".".join(str(p) for p in err.get("loc", [])), issue=err.get("msg", ""))
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            code=ErrorCode.VALIDATION_ERROR, message="Input validation failed",
            details=details,
            request_id=getattr(request.state, "request_id", str(uuid.uuid4())),
        ).model_dump(exclude_none=True),
    )


async def http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        code_map = {400: ErrorCode.BAD_REQUEST, 401: ErrorCode.AUTH_FAILED, 403: ErrorCode.FORBIDDEN, 404: ErrorCode.NOT_FOUND, 409: ErrorCode.CONFLICT, 429: ErrorCode.RATE_LIMITED}
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                code=code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR),
                message=str(exc.detail),
                request_id=getattr(request.state, "request_id", str(uuid.uuid4())),
            ).model_dump(exclude_none=True),
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            code=ErrorCode.INTERNAL_ERROR, message="An unexpected error occurred",
            request_id=getattr(request.state, "request_id", str(uuid.uuid4())),
        ).model_dump(exclude_none=True),
    )


def register_error_handlers(app) -> None:
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, http_error_handler)
