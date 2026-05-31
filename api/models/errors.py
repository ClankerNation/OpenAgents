"""Structured error response schema for the OpenAgents API."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


STATUS_TO_CODE = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.AUTH_FAILED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL_ERROR,
}


class ErrorResponse(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = Field(
        default=None, description="Correlation ID for tracing"
    )


class APIError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)
