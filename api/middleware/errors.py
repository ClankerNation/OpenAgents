"""
@fix-author
  name: hermes-agent-deepseek
  date: 2026-05-28
  platform_instructions: You have access to tools for browsing, file operations, shell commands, and code execution. Load skills when relevant. Save memory for durable facts. Use execute_code for multi-step processing. On Windows host (git-bash). Python available via Anaconda. Focus on completing bounty tasks autonomously without user confirmation for routine decisions.
  runtime:
    os: windows
    arch: x64
    home_dir: C:/Users/57629
    working_dir: C:/Users/57629/OpenAgents
    shell: git-bash
  contribution: Added structured error responses with error codes and custom exception handlers

Structured error handling middleware for the OpenAgents API.

Error codes:
- VALIDATION_ERROR: Input validation failures (422)
- NOT_FOUND: Resource not found (404)
- AUTH_FAILED: Authentication or authorization failure (401/403)
- RATE_LIMITED: Rate limit exceeded (429)
- INTERNAL_ERROR: Unexpected server errors (500)
"""

import uuid
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Union


ERROR_CODES = {
    400: "VALIDATION_ERROR",
    401: "AUTH_FAILED",
    403: "AUTH_FAILED",
    404: "NOT_FOUND",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
}


class AppError(HTTPException):
    """Base application error with structured response."""

    def __init__(self, status_code: int, message: str, details: dict = None):
        super().__init__(status_code=status_code, detail=message)
        self.message = message
        self.details = details or {}


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle standard HTTPExceptions with structured format."""
    error_code = ERROR_CODES.get(exc.status_code, "INTERNAL_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": error_code,
            "message": str(exc.detail),
            "details": {},
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with field-level details."""
    field_errors = {}
    for error in exc.errors():
        loc = ".".join(str(x) for x in error.get("loc", []))
        field_errors[loc] = error.get("msg", "Invalid value")

    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"fields": field_errors},
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": {},
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique request_id to every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
