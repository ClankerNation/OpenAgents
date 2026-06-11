# @generated-by: BountyHunter AI — Coder Agent
# @timestamp: 2026-06-10T01:40:00Z
# @runtime: Linux x86_64, /home/agent-the-coder/OpenAgents, /tmp/OpenAgents
"""
Structured error response middleware for the OpenAgents API.

Provides a standardized error response format with error codes,
human-readable messages, and optional detail payloads:

    {
        "error": {
            "code": "AUTH_ERROR",
            "message": "Invalid or expired authentication token",
            "details": {}
        }
    }
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Any, Optional

# ── Error Codes ────────────────────────────────────────────────────────

AUTH_ERROR = "AUTH_ERROR"
"""Authentication or authorization failure (401/403)."""

VALIDATION_ERROR = "VALIDATION_ERROR"
"""Request validation failure (422/400)."""

NOT_FOUND = "NOT_FOUND"
"""Resource not found (404)."""

RATE_LIMIT = "RATE_LIMIT"
"""Rate limit exceeded (429)."""

INTERNAL_ERROR = "INTERNAL_ERROR"
"""Unexpected server error (500)."""


# ── HTTP Status → Error Code Mapping ───────────────────────────────────

STATUS_TO_CODE: dict[int, str] = {
    400: VALIDATION_ERROR,
    401: AUTH_ERROR,
    403: AUTH_ERROR,
    404: NOT_FOUND,
    422: VALIDATION_ERROR,
    429: RATE_LIMIT,
    500: INTERNAL_ERROR,
}


def status_to_code(status_code: int) -> str:
    """Map an HTTP status code to the appropriate error code."""
    return STATUS_TO_CODE.get(status_code, INTERNAL_ERROR)


# ── Structured Exception ───────────────────────────────────────────────

class StructuredError(HTTPException):
    """
    HTTP exception with a machine-readable error code and optional details.

    Usage:
        raise StructuredError(
            status_code=401,
            code=AUTH_ERROR,
            message="Invalid or expired authentication token",
            details={"token_type": "access"},
        )

    The response body will be:
        {
            "error": {
                "code": "AUTH_ERROR",
                "message": "Invalid or expired authentication token",
                "details": {"token_type": "access"}
            }
        }
    """

    def __init__(
        self,
        status_code: int,
        code: Optional[str] = None,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.error_code = code or status_to_code(status_code)
        self.error_message = message or HTTPException(status_code=status_code).detail
        self.error_details = details or {}
        super().__init__(status_code=status_code, detail=self.error_message)


# ── Response Builder ───────────────────────────────────────────────────

def build_error_response(
    code: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a structured error response body."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


# ── FastAPI Exception Handler ──────────────────────────────────────────

async def structured_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    FastAPI exception handler that converts HTTPException and StructuredError
    into the standard structured error response format.
    """
    if isinstance(exc, StructuredError):
        code = exc.error_code
        details = exc.error_details
    else:
        # Convert plain HTTPException to structured format
        code = status_to_code(exc.status_code)
        details = {}

    body = build_error_response(
        code=code,
        message=str(exc.detail),
        details=details,
    )
    return JSONResponse(status_code=exc.status_code, content=body)


# ── Convenience Raisers ────────────────────────────────────────────────

def raise_auth_error(
    message: str = "Invalid or expired authentication token",
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Raise a structured 401 authentication error."""
    raise StructuredError(
        status_code=401,
        code=AUTH_ERROR,
        message=message,
        details=details,
    )


def raise_forbidden_error(
    message: str = "Insufficient permissions",
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Raise a structured 403 authorization error."""
    raise StructuredError(
        status_code=403,
        code=AUTH_ERROR,
        message=message,
        details=details,
    )


def raise_not_found_error(
    resource: str = "Resource",
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Raise a structured 404 not-found error."""
    raise StructuredError(
        status_code=404,
        code=NOT_FOUND,
        message=f"{resource} not found",
        details=details,
    )


def raise_validation_error(
    message: str = "Invalid request",
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Raise a structured 422 validation error."""
    raise StructuredError(
        status_code=422,
        code=VALIDATION_ERROR,
        message=message,
        details=details,
    )


def raise_rate_limit_error(
    message: str = "Too many requests. Please try again later.",
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Raise a structured 429 rate-limit error."""
    raise StructuredError(
        status_code=429,
        code=RATE_LIMIT,
        message=message,
        details=details,
    )


def raise_internal_error(
    message: str = "An unexpected error occurred",
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Raise a structured 500 internal error."""
    raise StructuredError(
        status_code=500,
        code=INTERNAL_ERROR,
        message=message,
        details=details,
    )