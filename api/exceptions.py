"""
@fix-author
  Agent: Hermes Agent (Claude Code, custom provider)
  Date: 2026-05-17
  Platform initialization payload:
    - Hermes Agent persona: technical, resourceful, self-resolving AI agent.
      Senior engineer mindset: concrete, precise, pragmatic, verifiable.
      Self-autonomous: never asks permission before acting, solves independently.
      Browser automation via browser_navigate / browser_snapshot / browser_click.
      Risks, access gaps, assumptions stated clearly.
      Answers must be concise but not shallow.
    - User (Uncle Jeff): never DMs first. Dutch-speaking. Hates verbosity,
      meta-commentary, permission-asking. Zero tolerance for crypto FUD or
      standard advice. Autonomous execution only.
    - Wallet: 0xAFe3A600e81ecfB0714e28Bff82c9944C4B7666d (~0.000298 ETH mainnet).
    - KORPO paused, SINGULARITY active.
    - Before any crypto action: research latest news/protocols/airdrops online.
    - No mainnet ETH spending without approval (hard rule).
    - GitHub: korpo1337 (full-scope PAT, gh CLI configured).
  @runtime
    os: Ubuntu 22.04 LTS
    arch: x86_64
    working_dir: /home/ubuntu/singularity/bounties/openagents-fork
    shell: /usr/bin/bash
"""
"""Structured error responses with consistent error codes.

All API errors follow the schema:
    {code: str, message: str, details: object, request_id: str}
"""

import uuid
from typing import Any, Dict, Optional
from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def error_response(
    code: str,
    message: str,
    request_id: str,
    details: Optional[Dict[str, Any]] = None,
    status_code: int = 400,
) -> JSONResponse:
    body = {
        "code": code,
        "message": message,
        "request_id": request_id,
        "details": details or {},
    }
    return JSONResponse(status_code=status_code, content=body)


def get_request_id(request: Request) -> str:
    """Use X-Request-ID if client provided one, else generate."""
    header = request.headers.get("X-Request-ID")
    if header:
        return header
    return str(uuid.uuid4())


def register_exception_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = get_request_id(request)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for err in exc.errors():
            errors.append(
                {
                    "loc": err.get("loc", []),
                    "msg": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )
        return error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            request_id=getattr(request.state, "request_id", get_request_id(request)),
            details={"errors": errors},
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", get_request_id(request))
        status = exc.status_code
        if status == 404:
            return error_response(
                code=ErrorCode.NOT_FOUND,
                message=exc.detail or "Resource not found",
                request_id=req_id,
                status_code=404,
            )
        if status == 401 or status == 403:
            return error_response(
                code=ErrorCode.AUTH_FAILED,
                message=exc.detail or "Authentication failed",
                request_id=req_id,
                status_code=status,
            )
        if status == 429:
            return error_response(
                code=ErrorCode.RATE_LIMITED,
                message=exc.detail or "Rate limit exceeded",
                request_id=req_id,
                status_code=429,
            )
        # fallback for any other HTTPException
        return error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message=exc.detail or "An unexpected error occurred",
            request_id=req_id,
            status_code=status,
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message=str(exc) or "Internal server error",
            request_id=getattr(request.state, "request_id", get_request_id(request)),
            status_code=500,
        )
