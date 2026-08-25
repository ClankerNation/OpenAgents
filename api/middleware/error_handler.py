"""Global exception handler for structured error responses.

Registers custom exception handlers on the FastAPI app to ensure all errors
follow the standardized ErrorResponse schema from issue #202.

@fix-author rafaio1
@date 2026-08-25T00:47:00Z
@runtime linux x64 /tmp/openagents_issue_202 bash
@platform-config Agentic bounty-hunter workflow
"""

import uuid
from typing import Any, Dict, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from pydantic import ValidationError

from ..errors import (
    create_error_response,
    create_validation_error,
    ErrorDetail,
    VALIDATION_ERROR,
    NOT_FOUND,
    AUTH_FAILED,
    FORBIDDEN,
    RATE_LIMITED,
    INTERNAL_ERROR,
    BAD_REQUEST,
)


def _get_request_id(request: Request) -> str:
    """Extract or generate request ID from headers."""
    return request.headers.get("x-request-id", str(uuid.uuid4()))


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTPException with structured response."""
    request_id = _get_request_id(request)
    
    code_map = {
        400: BAD_REQUEST,
        401: AUTH_FAILED,
        403: FORBIDDEN,
        404: NOT_FOUND,
        429: RATE_LIMITED,
    }
    code = code_map.get(exc.status_code, INTERNAL_ERROR)
    
    body = create_error_response(
        code=code,
        message=str(exc.detail),
        request_id=request_id,
    )
    
    return JSONResponse(status_code=exc.status_code, content=body)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with field-level details."""
    request_id = _get_request_id(request)
    
    field_errors: List[ErrorDetail] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        field = ".".join(str(part) for part in loc if part != "body") or "body"
        msg = error.get("msg", "Validation error")
        err_type = error.get("type", "value_error")
        
        field_errors.append(ErrorDetail(
            field=field,
            message=msg,
            code=err_type,
        ))
    
    body = create_validation_error(field_errors, request_id=request_id)
    return JSONResponse(status_code=422, content=body)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions."""
    request_id = _get_request_id(request)
    
    body = create_error_response(
        code=INTERNAL_ERROR,
        message="An unexpected error occurred",
        request_id=request_id,
    )
    
    return JSONResponse(status_code=500, content=body)


def register_error_handlers(app: FastAPI) -> None:
    """Register all structured error handlers on the FastAPI app."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
