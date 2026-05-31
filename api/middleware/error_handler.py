"""Custom exception handlers for structured error responses."""

import uuid
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from api.models.errors import ErrorResponse, ErrorCode


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with structured response."""
    request_id = str(uuid.uuid4())

    # Extract field-level validation details
    details = {
        "validation_errors": [
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
    }

    error_response = ErrorResponse(
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details=details,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.model_dump(),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with structured response."""
    request_id = str(uuid.uuid4())

    # Map status codes to error codes
    code_mapping = {
        404: ErrorCode.NOT_FOUND,
        401: ErrorCode.AUTH_FAILED,
        403: ErrorCode.AUTH_FAILED,
        429: ErrorCode.RATE_LIMITED,
        500: ErrorCode.INTERNAL_ERROR,
        502: ErrorCode.INTERNAL_ERROR,
        503: ErrorCode.INTERNAL_ERROR,
    }

    error_code = code_mapping.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    error_response = ErrorResponse(
        code=error_code,
        message=exc.detail if isinstance(exc.detail, str) else "An error occurred",
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions with structured response."""
    request_id = str(uuid.uuid4())

    error_response = ErrorResponse(
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal error occurred",
        details={"error_type": type(exc).__name__},
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
    )
