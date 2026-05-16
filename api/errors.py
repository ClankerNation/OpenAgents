"""
@fix-author
  name: Metatron
  date: 2026-05-16
  platform: Hermes Agent
  cron_job: 79683e6ae067
  session_identity: |
    Name: Metatron
    Creature: AI — the celestial scribe, greatest coder in the world
    Vibe: Serious, direct, no fluff. Speaks with authority.
  runtime:
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash
    python: 3.x

Structured error handling for the OpenAgents API.
Provides consistent error schema, typed exception classes, and FastAPI exception handlers.
"""

import uuid
import traceback
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
)


# ── Error codes ──────────────────────────────────────────────────────────────

class ErrorCode:
    """Well-known error codes returned by the API."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"


# ── Structured error response schema ─────────────────────────────────────────

@dataclass
class ErrorResponse:
    """Canonical error shape: {code, message, details, request_id}."""
    code: str
    message: str
    details: Any = None
    request_id: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "message": self.message}
        if self.details is not None:
            d["details"] = self.details
        if self.request_id is not None:
            d["request_id"] = self.request_id
        return d


# ── Typed application exceptions ─────────────────────────────────────────────

class AppError(HTTPException):
    """Base application exception — all handlers return ErrorResponse."""

    error_code: str = ErrorCode.INTERNAL_ERROR
    status_code: int = HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=self.status_code,
            detail={
                "code": self.error_code,
                "message": message,
                "details": details or {},
            },
            headers=headers,
        )
        self._app_message = message
        self._app_details = details


class NotFoundError(AppError):
    error_code = ErrorCode.NOT_FOUND
    status_code = HTTP_404_NOT_FOUND


class AuthFailedError(AppError):
    error_code = ErrorCode.AUTH_FAILED
    status_code = HTTP_401_UNAUTHORIZED


class ForbiddenError(AppError):
    error_code = ErrorCode.FORBIDDEN
    status_code = HTTP_403_FORBIDDEN


class RateLimitedError(AppError):
    error_code = ErrorCode.RATE_LIMITED
    status_code = HTTP_429_TOO_MANY_REQUESTS


class ConflictError(AppError):
    error_code = ErrorCode.CONFLICT
    status_code = 409


class BadRequestError(AppError):
    error_code = ErrorCode.BAD_REQUEST
    status_code = HTTP_400_BAD_REQUEST


# ── FastAPI exception handlers ───────────────────────────────────────────────

async def _get_request_id(request: Request) -> str:
    """Extract or generate a request ID."""
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    return rid


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle typed AppError exceptions."""
    request_id = await _get_request_id(request)
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": detail.get("code", exc.error_code),
            "message": detail.get("message", str(exc.detail)),
            "details": detail.get("details", {}),
            "request_id": request_id,
        },
        headers=getattr(exc, "headers", None) or {},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle generic HTTPExceptions — map status codes to error codes."""
    request_id = await _get_request_id(request)

    code_map = {
        400: ErrorCode.BAD_REQUEST,
        401: ErrorCode.AUTH_FAILED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        429: ErrorCode.RATE_LIMITED,
        409: ErrorCode.CONFLICT,
    }
    code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": str(exc.detail) if exc.detail else "An error occurred",
            "details": {},
            "request_id": request_id,
        },
        headers=getattr(exc, "headers", None) or {},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic/FastAPI validation errors with field-level details."""
    request_id = await _get_request_id(request)

    field_errors = []
    for error in exc.errors():
        field_errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "type": error["type"],
            "message": error["msg"],
        })

    return JSONResponse(
        status_code=HTTP_400_BAD_REQUEST,
        content={
            "code": ErrorCode.VALIDATION_ERROR,
            "message": "Request validation failed",
            "details": {"fields": field_errors},
            "request_id": request_id,
        },
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — never leak stack traces."""
    request_id = await _get_request_id(request)
    # Log the real error server-side but return a sanitized response
    traceback.print_exc()
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": ErrorCode.INTERNAL_ERROR,
            "message": "An unexpected error occurred",
            "details": {},
            "request_id": request_id,
        },
    )


# ── Convenience function: register all handlers on a FastAPI app ─────────────

def register_error_handlers(app):
    """Register all structured error handlers on a FastAPI application."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, internal_error_handler)
