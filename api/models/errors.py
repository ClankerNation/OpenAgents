"""Error models and exception classes for structured error responses."""

from typing import Optional, Any
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Structured error response schema."""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None
    request_id: Optional[str] = None


class APIError(Exception):
    """Base exception for API errors with structured responses."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class ValidationError(APIError):
    """Validation error with field-level details."""

    def __init__(self, message: str = "Validation failed", details: Optional[dict] = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
            details=details,
        )


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(self, message: str = "Resource not found", details: Optional[dict] = None):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=404,
            details=details,
        )


class AuthenticationError(APIError):
    """Authentication failed error."""

    def __init__(self, message: str = "Authentication failed", details: Optional[dict] = None):
        super().__init__(
            code="AUTH_FAILED",
            message=message,
            status_code=401,
            details=details,
        )


class RateLimitError(APIError):
    """Rate limit exceeded error."""

    def __init__(self, message: str = "Rate limit exceeded", details: Optional[dict] = None):
        super().__init__(
            code="RATE_LIMITED",
            message=message,
            status_code=429,
            details=details,
        )


class InternalError(APIError):
    """Internal server error."""

    def __init__(self, message: str = "Internal server error", details: Optional[dict] = None):
        super().__init__(
            code="INTERNAL_ERROR",
            message=message,
            status_code=500,
            details=details,
        )
