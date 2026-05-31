"""Structured error schema and handlers for the OpenAgents API."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


STATUS_CODE_TO_ERROR_CODE = {
    400: "BAD_REQUEST",
    401: "AUTH_FAILED",
    403: "AUTH_FAILED",
    404: "NOT_FOUND",
    429: "RATE_LIMITED",
}


def ensure_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid4())
    request.state.request_id = request_id
    return request_id


def make_error_payload(
    *,
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details or {},
        "request_id": request_id,
    }


def code_for_status(status_code: int) -> str:
    return STATUS_CODE_TO_ERROR_CODE.get(status_code, "INTERNAL_ERROR")


def details_from_validation(exc: RequestValidationError) -> dict[str, Any]:
    fields: dict[str, str] = {}
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", []) if part not in {"body", "query", "path"}]
        key = ".".join(loc) if loc else "request"
        fields[key] = error.get("msg", "Invalid value")
    return {"fields": fields}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = ensure_request_id(request)
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed"
    details = detail if isinstance(detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        content=make_error_payload(
            code=code_for_status(exc.status_code),
            message=message,
            details=details,
            request_id=request_id,
        ),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = ensure_request_id(request)
    return JSONResponse(
        status_code=422,
        content=make_error_payload(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=details_from_validation(exc),
            request_id=request_id,
        ),
    )


async def internal_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = ensure_request_id(request)
    return JSONResponse(
        status_code=500,
        content=make_error_payload(
            code="INTERNAL_ERROR",
            message="Internal server error",
            request_id=request_id,
        ),
    )
