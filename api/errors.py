"""
Structured error responses for OpenAgents API.

All errors follow schema: {code: string, message: string, details: object, request_id: string}
"""

import uuid
import time
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_MESSAGES = {
    ErrorCode.VALIDATION_ERROR: "Request validation failed",
    ErrorCode.NOT_FOUND: "Resource not found",
    ErrorCode.AUTH_FAILED: "Authentication failed",
    ErrorCode.AUTH_REQUIRED: "Authentication required",
    ErrorCode.FORBIDDEN: "Insufficient permissions",
    ErrorCode.RATE_LIMITED: "Rate limit exceeded",
    ErrorCode.CONFLICT: "Resource conflict",
    ErrorCode.INTERNAL_ERROR: "Internal server error",
}


def error_response(
    code: str,
    message: str = None,
    details: dict = None,
    request_id: str = None,
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message or ERROR_MESSAGES.get(code, "Unknown error"),
                "details": details or {},
                "request_id": request_id or str(uuid.uuid4()),
            }
        },
    )


class AppError(Exception):
    def __init__(self, code: str, message: str = None, details: dict = None, status_code: int = 400):
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, "Unknown error")
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return error_response(
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=request_id,
        status_code=exc.status_code,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    field_errors = {}
    for error in exc.errors():
        loc = error.get("loc", [])
        field = ".".join(str(l) for l in loc if l != "body")
        field_errors[field] = error.get("msg", "Invalid value")

    return error_response(
        code=ErrorCode.VALIDATION_ERROR,
        details={"fields": field_errors},
        request_id=request_id,
        status_code=422,
    )


async def http_exception_handler(request: Request, exc) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    status_code = exc.status_code
    detail = exc.detail if hasattr(exc, "detail") else str(exc)

    code_map = {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.AUTH_FAILED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        429: ErrorCode.RATE_LIMITED,
    }
    code = code_map.get(status_code, ErrorCode.INTERNAL_ERROR)

    return error_response(
        code=code,
        message=detail,
        request_id=request_id,
        status_code=status_code,
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return error_response(
        code=ErrorCode.INTERNAL_ERROR,
        request_id=request_id,
        status_code=500,
    )


def register_error_handlers(app):
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(404, http_exception_handler)
    app.add_exception_handler(401, http_exception_handler)
    app.add_exception_handler(403, http_exception_handler)
    app.add_exception_handler(429, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        return response
