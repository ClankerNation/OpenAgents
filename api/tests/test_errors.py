"""Tests for structured error responses."""

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from ..middleware.errors import (
    ERROR_CODES,
    AppError,
    http_exception_handler,
    validation_exception_handler,
    ERROR_CODES,
)


class MockRequest:
    class State:
        request_id = "test-123"

    def __init__(self):
        self.state = self.State()


# --- Test: Error codes defined ---

def test_error_codes_defined():
    """All required error codes should be in the mapping."""
    assert ERROR_CODES[400] == "VALIDATION_ERROR"
    assert ERROR_CODES[404] == "NOT_FOUND"
    assert ERROR_CODES[401] == "AUTH_FAILED"
    assert ERROR_CODES[403] == "AUTH_FAILED"
    assert ERROR_CODES[429] == "RATE_LIMITED"
    assert ERROR_CODES[422] == "VALIDATION_ERROR"
    assert ERROR_CODES[500] == "INTERNAL_ERROR"


# --- Test: HTTP exception handler ---

@pytest.mark.asyncio
async def test_not_found_error():
    """404 should return structured NOT_FOUND response."""
    req = MockRequest()
    exc = HTTPException(status_code=404, detail="Agent not found")
    resp = await http_exception_handler(req, exc)
    body = resp.body.decode()
    assert '"code":"NOT_FOUND"' in body
    assert '"message":"Agent not found"' in body
    assert '"request_id":"test-123"' in body


@pytest.mark.asyncio
async def test_auth_error():
    """401 should return structured AUTH_FAILED response."""
    req = MockRequest()
    exc = HTTPException(status_code=401, detail="Invalid token")
    resp = await http_exception_handler(req, exc)
    body = resp.body.decode()
    assert '"code":"AUTH_FAILED"' in body


# --- Test: Validation error handler ---

@pytest.mark.asyncio
async def test_validation_error_field_details():
    """Validation errors should include field-level details."""
    req = MockRequest()
    # Simulate a validation error
    mock_errors = [
        {"loc": ("body", "name"), "msg": "field required", "type": "value_error.missing"},
        {"loc": ("body", "amount"), "msg": "ensure this value is positive", "type": "value_error"},
    ]

    class MockValidationError(RequestValidationError):
        def __init__(self):
            self._errors = mock_errors

        def errors(self):
            return self._errors

    exc = MockValidationError()
    resp = await validation_exception_handler(req, exc)
    body = resp.body.decode()
    assert '"code":"VALIDATION_ERROR"' in body
    assert '"fields"' in body


# --- Test: AppError ---

def test_app_error():
    """AppError should carry status code, message, and details."""
    err = AppError(400, "Invalid input", {"field": "name"})
    assert err.status_code == 400
    assert err.message == "Invalid input"
    assert err.details == {"field": "name"}
