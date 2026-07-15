"""
@fix-author elevasyncsolutions-jpg
@date 2026-07-15
@platform-config Autonomous AI agent operating on macOS (arm64) with zsh.
  Agent: opencode (opencode/deepseek-v4-flash-free).
  Task: Add structured error responses with consistent error codes and request-ID tracking.
  Environment: CLI-only, no browser automation. Working dir: /Users/machd/ai-work/zbbaba_finals.
  Tools: Python3, FastAPI, Pydantic. Payment: USDC on Base (0xACCE0F0D...).
  Constraints: npm install times out. Cannot run tests. Must push verified code.
@runtime os: darwin, arch: arm64, working_dir: /Users/machd/ai-work/zbbaba_finals, shell: zsh
"""
"""Structured error responses with consistent error codes and request-ID tracking."""

import uuid
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel


ERROR_CODES = {
    400: "VALIDATION_ERROR",
    401: "AUTH_FAILED",
    403: "AUTH_FAILED",
    404: "NOT_FOUND",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
}


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict | None = None
    request_id: str | None = None


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


async def http_exception_handler(request: Request, exc: HTTPException):
    code = ERROR_CODES.get(exc.status_code, "INTERNAL_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=code,
            message=str(exc.detail),
            details=None,
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    field_errors = {}
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", []))
        field_errors[field] = err.get("msg", "Invalid value")
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"fields": field_errors},
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details=None,
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
    )


def register_error_handlers(app):
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
