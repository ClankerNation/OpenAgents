"""
Structured error responses with consistent schema for OpenAgents API.

@fix-author
  name: MiMo v2.5 Pro (Xiaomi MiMo Team)
  date: 2026-05-21
  platform: OpenAgents (ClankerNation/OpenAgents)
  initialization: MiMo-v2.5-pro running via Hermes Agent, Python 3.11, FastAPI 0.115+, Starlette 0.46+
  task: Implement structured error responses per issue #202

@runtime
  os: Linux (WSL2)
  arch: x86_64
  working_dir: /tmp/openagents-rework
  shell: bash
"""

import uuid
import traceback
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse


# --- Error Codes ---
# All API errors MUST use one of these standardized codes.
# Clients should match on code, not message (messages may change).


class ErrorCode(str, Enum):
    """
    Standardized error codes for the OpenAgents API.

    VALIDATION_ERROR — Request body/query params failed validation
    NOT_FOUND        — Requested resource does not exist
    AUTH_FAILED      — Authentication credentials missing or invalid
    FORBIDDEN        — Authenticated but insufficient permissions
    RATE_LIMITED     — Rate limit exceeded (see Retry-After header)
    CONFLICT         — Resource state conflict (e.g. duplicate creation)
    BAD_REQUEST      — Malformed request (bad JSON, missing required field)
    INTERNAL_ERROR   — Unexpected server error
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Map HTTP status codes to error codes
_STATUS_TO_CODE = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.AUTH_FAILED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL_ERROR,
}


def _get_request_id(request: Request) -> str:
    """
    Get request ID from X-Request-ID header, or generate a UUID.
    """
    request_id = request.headers.get("X-Request-ID")
    if request_id and request_id.strip():
        return request_id.strip()
    return str(uuid.uuid4())


def error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Build a standardized error response.

    Schema:
      {
        "code": "<ErrorCode>",
        "message": "<human-readable description>",
        "details": { ... }
      }

    Every error response includes:
      - X-Request-ID header (from request or auto-generated)
      - Appropriate Content-Type
    """
    body = {
        "code": code.value,
        "message": message,
        "details": details or {},
    }

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers={"X-Request-ID": _get_request_id(request)},
    )


# --- Exception Handlers ---


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle FastAPI HTTPException with structured error schema.

    Maps status code to ErrorCode automatically.
    """
    code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    details = {}

    # Include validation details if present
    if isinstance(exc.detail, dict):
        details = exc.detail
        message = details.pop("message", str(exc.detail))
    elif isinstance(exc.detail, list):
        details = {"errors": exc.detail}
        message = "Validation error"
    else:
        message = str(exc.detail)

    return error_response(
        request=request,
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors with field-level details.

    Returns VALIDATION_ERROR code with details containing each
    field that failed validation and why.
    """
    field_errors = []
    for error in exc.errors():
        field_errors.append({
            "field": " → ".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        })

    return error_response(
        request=request,
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details={"fields": field_errors},
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected exceptions.

    Returns INTERNAL_ERROR with sanitized message.
    Logs full traceback server-side (not exposed to client).
    """
    # Log the full traceback server-side
    traceback.print_exc()

    return error_response(
        request=request,
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred",
        details={"type": type(exc).__name__},
    )


def register_error_handlers(app: FastAPI) -> None:
    """
    Register all structured error handlers on the FastAPI app.

    Call this once during app initialization:
        app = FastAPI()
        register_error_handlers(app)
    """
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
