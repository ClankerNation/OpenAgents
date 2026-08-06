"""
Structured API error responses and request-ID propagation.

@fix-author: Codex
@date: 2026-08-06
@platform-instructions: Private session and startup instructions intentionally omitted.
@runtime: os=Darwin, arch=arm64, home_dir=[redacted], working_dir=[redacted], shell=zsh
"""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request


ERROR_CODES = {
    401: "AUTH_FAILED",
    403: "AUTH_FAILED",
    404: "NOT_FOUND",
    429: "RATE_LIMITED",
}


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get(
        "X-Request-ID"
    ) or str(uuid4())


def _http_error_code(status_code: int) -> str:
    if status_code in ERROR_CODES:
        return ERROR_CODES[status_code]
    if 400 <= status_code < 500:
        return "VALIDATION_ERROR"
    return "INTERNAL_ERROR"


def _detail_object(detail: Any) -> dict[str, Any]:
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, list):
        return {"errors": detail}
    if detail is None:
        return {}
    return {"detail": detail}


def _message_for_detail(detail: Any) -> str:
    return detail if isinstance(detail, str) else "Request failed"


def _response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        code=code,
        message=message,
        details=details,
        request_id=_request_id(request),
    ).model_dump()
    return JSONResponse(status_code=status_code, content=payload, headers=headers)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _response(
        request=request,
        status_code=exc.status_code,
        code=_http_error_code(exc.status_code),
        message=_message_for_detail(exc.detail),
        details=_detail_object(exc.detail),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields: dict[str, list[str]] = {}
    errors: list[dict[str, Any]] = []

    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ())]
        field = ".".join(location) or "request"
        message = str(error.get("msg", "Invalid value"))
        fields.setdefault(field, []).append(message)
        errors.append({"loc": location, "msg": message, "type": error.get("type")})

    return _response(
        request=request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"fields": fields, "errors": errors},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _response(
        request=request,
        status_code=500,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        details={},
    )


class RequestIDMiddleware:
    """Attach one stable request ID to state, headers, and error payloads."""

    def __init__(self, app: Callable[..., Any]):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming_request_id = next(
            (
                value.decode("latin-1")
                for key, value in scope.get("headers", [])
                if key.lower() == b"x-request-id" and value.strip()
            ),
            None,
        )
        request_id = incoming_request_id or str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def register_error_handlers(app: Any) -> None:
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(FastAPIHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
