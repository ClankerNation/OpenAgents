"""Structured API error response helpers."""

from typing import Any, Optional

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: Optional[str] = None
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class APIError(Exception):
    """Application exception with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found", details: Optional[dict[str, Any]] = None):
        super().__init__("NOT_FOUND", message, 404, details)

