"""Structured error handling for the OpenAgents API."""

import uuid
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

class APIError(Exception):
    """Base class for custom API errors."""
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found", details: dict = None):
        super().__init__(code="NOT_FOUND", message=message, status_code=404, details=details)

class AuthFailedError(APIError):
    def __init__(self, message: str = "Authentication failed", details: dict = None):
        super().__init__(code="AUTH_FAILED", message=message, status_code=401, details=details)

class RateLimitedError(APIError):
    def __init__(self, message: str = "Rate limit exceeded", details: dict = None, retry_after: int = 60):
        super().__init__(code="RATE_LIMITED", message=message, status_code=429, details=details)
        self.retry_after = retry_after

class InternalError(APIError):
    def __init__(self, message: str = "Internal server error", details: dict = None):
        super().__init__(code="INTERNAL_ERROR", message=message, status_code=500, details=details)

def get_request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID", str(uuid.uuid4()))

async def api_error_handler(request: Request, exc: APIError):
    request_id = get_request_id(request)
    content = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": request_id,
        }
    }
    headers = {"X-Request-ID": request_id}
    if hasattr(exc, "retry_after"):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(status_code=exc.status_code, content=content, headers=headers)

async def validation_error_handler(request: Request, exc: RequestValidationError):
    request_id = get_request_id(request)
    details = {}
    for err in exc.errors():
        loc = ".".join(str(l) for l in err.get("loc", []))
        if loc not in details:
            details[loc] = []
        details[loc].append(err.get("msg", "Invalid value"))
    
    content = {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": details,
            "request_id": request_id,
        }
    }
    return JSONResponse(status_code=422, content=content, headers={"X-Request-ID": request_id})

async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = get_request_id(request)
    code_map = {
        400: "BAD_REQUEST",
        401: "AUTH_FAILED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
    }
    code = code_map.get(exc.status_code, "API_ERROR")
    content = {
        "error": {
            "code": code,
            "message": exc.detail,
            "details": {},
            "request_id": request_id,
        }
    }
    return JSONResponse(status_code=exc.status_code, content=content, headers={"X-Request-ID": request_id})

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = get_request_id(request)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
