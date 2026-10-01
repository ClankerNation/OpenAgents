"""Structured error responses for the OpenAgents API.

All API errors are serialized as a single consistent schema:

    {"code": str, "message": str, "details": object, "request_id": str}

``code`` is always one of the values in :class:`ErrorCode`. Request handlers
should raise :class:`APIError` (or one of its subclasses) instead of
returning ad-hoc error payloads; FastAPI's default ``HTTPException`` and
validation errors are also normalized to this schema by the handlers
registered in :func:`register_exception_handlers`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse


class ErrorCode(str, Enum):
    """Canonical error codes returned by the API."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Error codes that are safe to expose for any HTTP status code that doesn't
# map onto something more specific below.
_STATUS_TO_CODE = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.AUTH_FAILED,
    403: ErrorCode.AUTH_FAILED,
    404: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}

_CODE_TO_STATUS = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.AUTH_FAILED: 401,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
}


class ErrorResponse(BaseModel):
    """Response body schema for every error the API returns."""

    code: ErrorCode
    message: str
    details: dict = {}
    request_id: Optional[str] = None


class APIError(Exception):
    """Base exception for all structured API errors.

    Raise this (or a subclass) from route handlers instead of
    ``HTTPException`` to get full control over ``code`` and ``details``.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[dict] = None,
        status_code: Optional[int] = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code or _CODE_TO_STATUS.get(code, 500)
        super().__init__(message)


class ValidationAPIError(APIError):
    def __init__(self, message: str = "Validation failed", details: Optional[dict] = None):
        super().__init__(ErrorCode.VALIDATION_ERROR, message, details)


class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found", details: Optional[dict] = None):
        super().__init__(ErrorCode.NOT_FOUND, message, details)


class AuthFailedError(APIError):
    def __init__(self, message: str = "Authentication failed", details: Optional[dict] = None):
        super().__init__(ErrorCode.AUTH_FAILED, message, details)


class RateLimitedError(APIError):
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[dict] = None):
        super().__init__(ErrorCode.RATE_LIMITED, message, details)


class InternalError(APIError):
    def __init__(self, message: str = "Internal server error", details: Optional[dict] = None):
        super().__init__(ErrorCode.INTERNAL_ERROR, message, details)


def _get_request_id(request: Request) -> Optional[str]:
    return getattr(request.state, "request_id", None)


def _error_json(
    request: Request, status_code: int, code: ErrorCode, message: str, details: Any = None
) -> JSONResponse:
    body = ErrorResponse(
        code=code,
        message=message,
        details=details or {},
        request_id=_get_request_id(request),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that normalize every error response to the shared schema."""

    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return _error_json(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = []
        for err in exc.errors():
            fields.append(
                {
                    "field": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                    "message": err.get("msg"),
                    "type": err.get("type"),
                }
            )
        return _error_json(
            request,
            400,
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _STATUS_TO_CODE.get(
            exc.status_code,
            ErrorCode.VALIDATION_ERROR if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR,
        )
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return _error_json(request, exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return _error_json(request, 500, ErrorCode.INTERNAL_ERROR, "Internal server error")
