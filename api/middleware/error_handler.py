"""Exception handlers for structured API error responses."""

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from ..models.errors import APIError, ErrorDetail, ErrorResponse
except ImportError:  # Allows `cd api && uvicorn main:app`.
    from models.errors import APIError, ErrorDetail, ErrorResponse


logger = logging.getLogger(__name__)


def status_to_code(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "AUTHENTICATION_ERROR",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "HTTP_ERROR")


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error = ErrorDetail(
        code=code,
        message=message,
        details=details,
        request_id=request_id,
    )
    body = ErrorResponse(
        error=error,
        request_id=request_id,
        code=code,
        message=message,
        details=details,
    ).model_dump(exclude_none=True)
    response = JSONResponse(status_code=status_code, content=body, headers=headers)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=getattr(request.state, "request_id", None),
    )


async def http_error_handler(
    request: Request, exc: HTTPException | StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    details = None if isinstance(exc.detail, str) else {"detail": exc.detail}
    return build_error_response(
        status_code=exc.status_code,
        code=status_to_code(exc.status_code),
        message=detail,
        details=details,
        request_id=getattr(request.state, "request_id", None),
        headers=getattr(exc, "headers", None),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = {
        "validation_errors": [
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
    }
    return build_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=details,
        request_id=getattr(request.state, "request_id", None),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API exception", exc_info=exc)
    return build_error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="Internal server error",
        request_id=getattr(request.state, "request_id", None),
    )

