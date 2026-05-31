"""Structured error handler for OpenAgents API.

Contributor: Claude (Anthropic AI Assistant)
Platform: Claude 3.5 Sonnet on Anthropic
Runtime: Python 3.11
OS: darwin | Arch: arm64 | WD: /api | Shell: /bin/zsh
Init: You are opencode, CLI tool for software engineering. Env: macOS darwin arm64 zsh Python 3.11.
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import contextvars

request_id_var = contextvars.ContextVar("request_id", default="")

ERROR_CODES = {
    "VALIDATION_ERROR": "ERR_001",
    "NOT_FOUND": "ERR_002",
    "AUTH_FAILED": "ERR_003",
    "RATE_LIMITED": "ERR_004",
    "INTERNAL_ERROR": "ERR_005",
}

async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = request_id_var.get()
    if isinstance(exc, HTTPException):
        code = ERROR_CODES.get(str(exc.status_code), "ERR_005")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": code,
                "message": str(exc.detail),
                "details": getattr(exc, "details", None),
                "request_id": rid,
            },
        )
    return JSONResponse(
        status_code=500,
        content={
            "code": "ERR_005",
            "message": "Internal server error",
            "details": None,
            "request_id": rid,
        },
    )
