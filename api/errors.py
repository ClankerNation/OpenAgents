"""Structured API error responses."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

ERROR_CODE_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
    status.HTTP_401_UNAUTHORIZED: "AUTH_FAILED",
    status.HTTP_403_FORBIDDEN: "AUTH_FAILED",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
}

ERROR_MESSAGE_BY_CODE = {
    "VALIDATION_ERROR": "Request validation failed",
    "NOT_FOUND": "Resource not found",
    "AUTH_FAILED": "Authentication failed",
    "RATE_LIMITED": "Rate limit exceeded",
    "INTERNAL_ERROR": "Internal server error",
}


def request_id_for(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return request_id
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    return request_id


def error_code_for_status(status_code: int) -> str:
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return ERROR_CODE_BY_STATUS.get(status_code, "VALIDATION_ERROR")


def error_response(
    request: Request,
    status_code: int,
    code: str | None = None,
    message: str | None = None,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    resolved_code = code or error_code_for_status(status_code)
    response = JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": resolved_code,
                "message": message or ERROR_MESSAGE_BY_CODE.get(resolved_code, "Request failed"),
                "details": details,
                "request_id": request_id_for(request),
            }
        },
        headers=headers,
    )
    response.headers["X-Request-ID"] = request_id_for(request)
    return response


def validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    details = []
    for error in exc.errors():
        field_path = ".".join(str(part) for part in error.get("loc", []) if part != "body")
        details.append(
            {
                "field": field_path,
                "message": error.get("msg"),
                "type": error.get("type"),
            }
        )
    return details


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
        return error_response(
            request,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=validation_details(exc),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code = error_code_for_status(exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) else ERROR_MESSAGE_BY_CODE.get(code)
        details = None if isinstance(exc.detail, str) else exc.detail
        return error_response(
            request,
            exc.status_code,
            code=code,
            message=message,
            details=details,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="Internal server error",
            details=None,
        )
