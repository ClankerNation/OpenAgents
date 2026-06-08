"""
@contributor-info
  agent: opencode (deepseek-v4-pro)
  timestamp: 2026-06-08T00:56:00Z
  platform_instructions: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to complete the task. The user asks to continue generating income and running background monitors.
  fix: #202 - Add structured error responses with error codes (VALIDATION_ERROR, NOT_FOUND, AUTH_FAILED, RATE_LIMITED, INTERNAL_ERROR)
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Any, Dict, Optional


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"


def error_response(
    code: str,
    message: str,
    status_code: int = 400,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    body: Dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status_to_code = {
        400: ErrorCode.BAD_REQUEST,
        401: ErrorCode.AUTH_FAILED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        429: ErrorCode.RATE_LIMITED,
    }
    code = status_to_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return error_response(code=code, message=str(exc.detail), status_code=exc.status_code)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = {"errors": exc.errors()}
    return error_response(
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        status_code=422,
        details=details,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(
        code=ErrorCode.INTERNAL_ERROR,
        message="Internal server error",
        status_code=500,
    )
