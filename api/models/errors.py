"""Structured error response schema and error code constants.

All API errors follow the schema:
    {"code": str, "message": str, "details": dict, "request_id": str}

Error codes are stable identifiers that clients can branch on without
parsing human-readable messages.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ErrorCode:
    """Canonical error codes returned by the API."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


HTTP_STATUS_TO_CODE = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.AUTH_FAILED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


class ErrorResponse(BaseModel):
    code: str = Field(..., description="Stable error code identifier")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] = Field(default_factory=dict, description="Error-specific context")
    request_id: Optional[str] = Field(None, description="Request identifier for correlation")
