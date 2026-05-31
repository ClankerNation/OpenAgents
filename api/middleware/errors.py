from enum import Enum
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMIT = "RATE_LIMIT"
    CONFLICT = "CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    PAYMENT_ERROR = "PAYMENT_ERROR"
    TASK_ERROR = "TASK_ERROR"
    AGENT_ERROR = "AGENT_ERROR"


ERROR_STATUS_MAP = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.AUTH_ERROR: 401,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.RATE_LIMIT: 429,
    ErrorCode.CONFLICT: 409,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.DUPLICATE_ENTRY: 409,
    ErrorCode.PAYMENT_ERROR: 400,
    ErrorCode.TASK_ERROR: 400,
    ErrorCode.AGENT_ERROR: 400,
}


def error_response(code: ErrorCode, message: str, details: dict = None):
    resp = {"success": False, "error": {"code": code.value, "message": message}}
    if details:
        resp["error"]["details"] = details
    return resp


class AppHTTPException(HTTPException):
    def __init__(self, error_code: ErrorCode, message: str, details: dict = None):
        self.error_code = error_code
        status_code = ERROR_STATUS_MAP.get(error_code, 500)
        super().__init__(status_code=status_code, detail=error_response(error_code, message, details))


async def app_exception_handler(request: Request, exc: AppHTTPException):
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


async def http_exception_handler(request: Request, exc: HTTPException):
    code = ErrorCode.INTERNAL_ERROR
    if exc.status_code == 404:
        code = ErrorCode.NOT_FOUND
    elif exc.status_code == 401:
        code = ErrorCode.AUTH_ERROR
    elif exc.status_code == 403:
        code = ErrorCode.FORBIDDEN
    elif exc.status_code == 400:
        code = ErrorCode.VALIDATION_ERROR
    elif exc.status_code == 409:
        code = ErrorCode.CONFLICT
    elif exc.status_code == 429:
        code = ErrorCode.RATE_LIMIT
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(code, str(exc.detail)),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_response(
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed",
            {"errors": exc.errors()},
        ),
    )


async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=error_response(
            ErrorCode.INTERNAL_ERROR,
            "An unexpected error occurred",
        ),
    )
