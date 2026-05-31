"""Global error handler middleware for structured error responses."""

import uuid
import traceback
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from ..models.errors import ErrorResponse, ErrorCode, APIError, STATUS_TO_CODE


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())

    error_response = ErrorResponse(
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())

    code = STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    error_response = ErrorResponse(
        code=code,
        message=str(exc.detail),
        details={},
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())

    field_errors = {}
    for error in exc.errors():
        field_path = ".".join(str(loc) for loc in error["loc"])
        field_errors[field_path] = {
            "message": error["msg"],
            "type": error["type"],
        }

    error_response = ErrorResponse(
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details={"fields": field_errors},
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())

    # Log the full traceback for debugging
    print(f"Unhandled exception for request {request_id}:")
    traceback.print_exc()

    error_response = ErrorResponse(
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal error occurred",
        details={"type": type(exc).__name__},
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
    )


def register_error_handlers(app):
    """Register all error handlers with the FastAPI app."""
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
