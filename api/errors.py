"""Structured error codes, schema, and custom exceptions for the OpenAgents API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from fastapi import HTTPException


class ErrorCode(str, Enum):
    """Canonical error codes returned by every API error endpoint."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Auth failed is a special case mapped from HTTP 401
AUTH_FAILED="AUTH_FAILED"

class ValidationErrorDetail(BaseModel):
    """Single-field validation error detail."""

    loc: list[str] = Field(default_factory=list, description="Error location (e.g. body, field_name)")
    msg: str = Field(default="", description="Human-readable message")
    type: str = Field(default="", description="Pydantic error type")


class ErrorResponse(BaseModel):
    """Standard API error response body."""

    code: str
    message: str
    details: Optional[Any] = None
    request_id: Optional[str] = None


class AppException(HTTPException):
    """Base application exception that carries a structured error code."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Any = None,
        headers: Optional[dict] = None,
    ):
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.details = details


class NotFoundException(AppException):
    def __init__(self, resource: str = "Resource", resource_id: Any = None):
        msg = f"{resource} not found"
        if resource_id is not None:
            msg = f"{resource} '{resource_id}' not found"
        super().__init__(code=ErrorCode.NOT_FOUND, message=msg, status_code=404)


class AuthFailedException(AppException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(code=AUTH_FAILED, message=message, status_code=401)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(code=ErrorCode.FORBIDDEN, message=message, status_code=403)


class RateLimitedException(AppException):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message="Rate limit exceeded",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )


class InternalErrorException(AppException):
    def __init__(self, message: str = "Internal server error"):
        super().__init__(code=ErrorCode.INTERNAL_ERROR, message=message, status_code=500)
