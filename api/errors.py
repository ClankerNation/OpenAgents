"""Structured error responses for the OpenAgents API.

Implements consistent error schema with error codes, field-level validation
details, and request_id tracing per issue #202 requirements.

@fix-author rafaio1
@date 2026-08-25T00:45:00Z
@runtime linux x64 /tmp/openagents_issue_202 bash
@platform-config Agentic bounty-hunter workflow
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class ErrorDetail(BaseModel):
    """Field-level error detail for validation errors."""
    field: str = Field(..., description="The field that caused the error")
    message: str = Field(..., description="Human-readable error message")
    code: str = Field(..., description="Machine-readable error code for this field")


class ErrorResponse(BaseModel):
    """Standardized error response schema.
    
    All API errors MUST follow this structure for consistency.
    """
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional context or field-level errors")
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique request identifier for tracing")


# Standard error codes
VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
AUTH_FAILED = "AUTH_FAILED"
RATE_LIMITED = "RATE_LIMITED"
INTERNAL_ERROR = "INTERNAL_ERROR"
FORBIDDEN = "FORBIDDEN"
CONFLICT = "CONFLICT"
BAD_REQUEST = "BAD_REQUEST"


def create_error_response(
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a standardized error response dict.
    
    Args:
        code: Machine-readable error code
        message: Human-readable error description  
        details: Optional additional context or field-level errors
        request_id: Optional request ID (auto-generated if not provided)
        
    Returns:
        Dict matching ErrorResponse schema
    """
    return ErrorResponse(
        code=code,
        message=message,
        details=details,
        request_id=request_id or str(uuid.uuid4()),
    ).model_dump()


def create_validation_error(
    field_errors: List[ErrorDetail],
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a validation error response with field-level details.
    
    Args:
        field_errors: List of field-specific error details
        request_id: Optional request ID
        
    Returns:
        Dict matching ErrorResponse schema with VALIDATION_ERROR code
    """
    return create_error_response(
        code=VALIDATION_ERROR,
        message="Request validation failed",
        details={"fields": [fe.model_dump() for fe in field_errors]},
        request_id=request_id,
    )
