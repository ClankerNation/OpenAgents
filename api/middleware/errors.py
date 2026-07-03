"""
Structured error responses with error codes for the OpenAgents API.

Provides:
- ErrorCode: Enum of standardised error codes
- APIError: Exception class that wraps error codes, status codes, and details
- build_error_response: Builds a standard JSON error dict
- StructuredErrorMiddleware: FastAPI middleware that catches APIError and
  unhandled exceptions, returning consistent structured responses
"""

from enum import Enum
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ErrorCode(str, Enum):
    """Canonical error codes returned by the OpenAgents API."""

    # ── General ────────────────────────────────────────────────────────────
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT = "CONFLICT"
    UNPROCESSABLE_ENTITY = "UNPROCESSABLE_ENTITY"

    # ── Authentication / Authorisation ─────────────────────────────────────
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    INSUFFICIENT_ROLE = "INSUFFICIENT_ROLE"

    # ── Rate Limiting ──────────────────────────────────────────────────────
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # ── Resource-specific ──────────────────────────────────────────────────
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    PAYMENT_NOT_FOUND = "PAYMENT_NOT_FOUND"
    ESCROW_NOT_FOUND = "ESCROW_NOT_FOUND"
    TASK_NOT_COMPLETED = "TASK_NOT_COMPLETED"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"

    # ── Business Logic ─────────────────────────────────────────────────────
    INVALID_STATUS_TRANSITION = "INVALID_STATUS_TRANSITION"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    ESCROW_EXHAUSTED = "ESCROW_EXHAUSTED"
    AGENT_NOT_OWNER = "AGENT_NOT_OWNER"
    INVALID_TASK_STATE = "INVALID_TASK_STATE"


# Mapping from ErrorCode to default HTTP status code
_ERROR_CODE_TO_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.CONFLICT: 409,
    ErrorCode.UNPROCESSABLE_ENTITY: 422,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.INVALID_TOKEN: 401,
    ErrorCode.INSUFFICIENT_ROLE: 403,
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    ErrorCode.AGENT_NOT_FOUND: 404,
    ErrorCode.TASK_NOT_FOUND: 404,
    ErrorCode.PAYMENT_NOT_FOUND: 404,
    ErrorCode.ESCROW_NOT_FOUND: 404,
    ErrorCode.TASK_NOT_COMPLETED: 400,
    ErrorCode.DUPLICATE_ENTRY: 409,
    ErrorCode.INVALID_STATUS_TRANSITION: 400,
    ErrorCode.INSUFFICIENT_FUNDS: 400,
    ErrorCode.ESCROW_EXHAUSTED: 400,
    ErrorCode.AGENT_NOT_OWNER: 403,
    ErrorCode.INVALID_TASK_STATE: 400,
}


class APIError(Exception):
    """
    Application-level exception with a structured error code.

    Usage::

        raise APIError(ErrorCode.AGENT_NOT_FOUND, detail="Agent 42 not found")
        raise APIError(ErrorCode.FORBIDDEN, detail="Not the owner")

    When caught by ``StructuredErrorMiddleware`` it produces a consistent
    JSON body::

        {
            "error": {
                "code": "AGENT_NOT_FOUND",
                "message": "Agent 42 not found",
                "status_code": 404
            }
        }
    """

    def __init__(
        self,
        code: ErrorCode,
        detail: str = "",
        status_code: Optional[int] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        self.code = code
        self.detail = detail or code.value.replace("_", " ").title()
        self.status_code = status_code or _ERROR_CODE_TO_STATUS.get(code, 500)
        self.extra = extra or {}
        super().__init__(self.detail)

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.detail}"


def build_error_response(
    code: ErrorCode,
    message: str,
    status_code: int,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a standardised error response dictionary.

    This is a pure helper — useful when you want to return a JSONResponse
    directly without raising (e.g. inside middleware ``dispatch`` methods).
    """
    body: dict[str, Any] = {
        "error": {
            "code": code.value,
            "message": message,
            "status_code": status_code,
        }
    }
    if extra:
        body["error"]["extra"] = extra
    return body


class StructuredErrorMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that catches ``APIError`` and unhandled ``Exception``
    and returns a consistent structured JSON error response.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except APIError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=build_error_response(
                    code=exc.code,
                    message=exc.detail,
                    status_code=exc.status_code,
                    extra=exc.extra or None,
                ),
            )
        except Exception as exc:
            # Log the real error in production; return a safe generic message
            # in the response so we don't leak internals.
            return JSONResponse(
                status_code=500,
                content=build_error_response(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="An unexpected error occurred",
                    status_code=500,
                ),
            )
