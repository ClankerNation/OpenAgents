# @fix-author rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Structured error responses for the OpenAgents API."""

import uuid
from typing import Optional, Any
from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorCodes:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def make_error_response(
    code: str,
    message: str,
    status_code: int,
    details: Optional[Any] = None,
    request_id: Optional[str] = None,
) -> JSONResponse:
    """Create a standardized error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id or str(uuid.uuid4()),
        },
    )


async def validation_exception_handler(request: Request, exc):
    """Handle Pydantic/FastAPI validation errors with field-level details."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    errors = []
    for err in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in err.get("loc", [])),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })
    return make_error_response(
        code=ErrorCodes.VALIDATION_ERROR,
        message="Request validation failed",
        status_code=422,
        details={"errors": errors},
        request_id=request_id,
    )


async def http_exception_handler(request: Request, exc):
    """Map HTTPException to structured error codes."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    # Map status codes to error codes
    code_map = {
        400: ErrorCodes.VALIDATION_ERROR,
        401: ErrorCodes.AUTH_FAILED,
        403: ErrorCodes.AUTH_FAILED,
        404: ErrorCodes.NOT_FOUND,
        429: ErrorCodes.RATE_LIMITED,
    }
    code = code_map.get(exc.status_code, ErrorCodes.INTERNAL_ERROR)
    
    return make_error_response(
        code=code,
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id,
    )


async def generic_exception_handler(request: Request, exc):
    """Catch-all for unhandled exceptions."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return make_error_response(
        code=ErrorCodes.INTERNAL_ERROR,
        message="An unexpected error occurred",
        status_code=500,
        request_id=request_id,
    )
