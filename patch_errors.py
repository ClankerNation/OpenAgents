import re

with open('api/main.py', 'r') as f:
    content = f.read()

# Add contributor header at the very top
header = """\"\"\"
OpenAgents API Entry Point
@contributor-info ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
\"\"\"
"""
if not content.startswith('"""\nOpenAgents API Entry Point\n@contributor-info'):
    # Remove existing docstring if present
    content = re.sub(r'^""".*?"""\s*', '', content, flags=re.DOTALL)
    content = header + content

# Add imports and error models after existing imports
imports_addition = """from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
import uuid
"""

# Replace existing imports block
content = re.sub(
    r'from fastapi import FastAPI, HTTPException, Query\nfrom pydantic import BaseModel\nfrom typing import Optional\nfrom datetime import datetime\n',
    imports_addition,
    content
)

# Add error response models and exception handlers before app definition
error_models = """
# Structured Error Response Schema
class ErrorResponse(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Any] = Field(None, description="Additional error context")
    request_id: Optional[str] = Field(None, description="Request correlation ID")


# Custom Exception Classes
class AppException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(status_code=status_code, detail=message)


# Exception Handlers
async def app_exception_handler(request: Request, exc: AppException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": request_id,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    # Map status codes to error codes
    code_map = {
        400: "VALIDATION_ERROR",
        401: "AUTH_FAILED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
    }
    code = code_map.get(exc.status_code, "ERROR")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "details": None,
            "request_id": request_id,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    # Extract field-level details
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })
    
    return JSONResponse(
        status_code=400,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"errors": errors},
            "request_id": request_id,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": None,
            "request_id": request_id,
        },
    )

"""

# Insert error models before app = FastAPI(...)
content = content.replace("app = FastAPI(", error_models + "\napp = FastAPI(")

# Update app definition to include exception handlers
old_app_def = '''app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)'''

new_app_def = '''app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    responses={
        400: {"model": ErrorResponse, "description": "Validation or bad request error"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        403: {"model": ErrorResponse, "description": "Forbidden access"},
        404: {"model": ErrorResponse, "description": "Resource not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)

# Register exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)'''

content = content.replace(old_app_def, new_app_def)

with open('api/main.py', 'w') as f:
    f.write(content)

print("Patched api/main.py with structured error responses")
