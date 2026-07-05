"""
@generated-by: opencode
@platform: OpenCode (opencode.ai)
@timestamp: 2026-07-05T00:00:00+05:30
@session: This file was modified as part of the OpenAgents bounty program.
"""

"""Structured error responses and request ID middleware for OpenAgents API."""

import uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Any, Dict, Optional


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: str


def add_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details={"errors": exc.errors()},
                request_id=getattr(request.state, "request_id", ""),
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code_map = {
            400: "VALIDATION_ERROR",
            401: "AUTH_FAILED",
            403: "AUTH_FAILED",
            404: "NOT_FOUND",
                415: "VALIDATION_ERROR",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                code=code_map.get(exc.status_code, "INTERNAL_ERROR"),
                message=str(exc.detail),
                request_id=getattr(request.state, "request_id", ""),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred",
                details={"type": type(exc).__name__},
                request_id=getattr(request.state, "request_id", ""),
            ).model_dump(),
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                code="NOT_FOUND",
                message="The requested resource was not found",
                request_id=getattr(request.state, "request_id", ""),
            ).model_dump(),
        )


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response
