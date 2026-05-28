"""Standardized error responses for the OpenAgents API."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel
from fastapi import Request
from starlette.responses import JSONResponse
import uuid


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorResponse(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = {}
    request_id: str


class APIError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int,
        details: Optional[dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(APIError):
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            status_code=404,
            details={"resource": resource, "identifier": str(identifier)},
        )


class AuthError(APIError):
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.AUTH_FAILED,
            message=message,
            status_code=401,
            details=details or {},
        )


class ForbiddenError(APIError):
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.AUTH_FAILED,
            message=message,
            status_code=403,
            details=details or {},
        )


class ValidationError(APIError):
    def __init__(self, message: str, fields: Optional[list[dict[str, Any]]] = None):
        details: dict[str, Any] = {}
        if fields:
            details["fields"] = fields
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            status_code=422,
            details=details,
        )


class RateLimitError(APIError):
    def __init__(self, retry_after: int):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message="Rate limit exceeded",
            status_code=429,
            details={"retry_after": retry_after},
        )


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=_get_request_id(request),
        ).model_dump(),
    )


async def validation_error_handler(request, exc) -> JSONResponse:
    fields = []
    for error in exc.errors():
        fields.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            details={"fields": fields},
            request_id=_get_request_id(request),
        ).model_dump(),
    )


async def http_exception_handler(request: Request, exc) -> JSONResponse:
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", "Internal server error")

    code = ErrorCode.INTERNAL_ERROR
    if status_code == 401:
        code = ErrorCode.AUTH_FAILED
    elif status_code == 403:
        code = ErrorCode.AUTH_FAILED
    elif status_code == 404:
        code = ErrorCode.NOT_FOUND
    elif status_code == 429:
        code = ErrorCode.RATE_LIMITED
    elif status_code == 422:
        code = ErrorCode.VALIDATION_ERROR

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            code=code,
            message=str(detail),
            details={},
            request_id=_get_request_id(request),
        ).model_dump(),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message="Internal server error",
            details={},
            request_id=_get_request_id(request),
        ).model_dump(),
    )
