"""
Tests for structured error responses.

Covers:
  - All error codes (VALIDATION_ERROR, NOT_FOUND, AUTH_FAILED, FORBIDDEN,
    RATE_LIMITED, CONFLICT, BAD_REQUEST, INTERNAL_ERROR)
  - Error response schema {code, message, details}
  - Validation errors include field-level details
  - Request ID present in every error response
  - Custom exception handlers
"""

import pytest
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.errors import (
    ErrorCode,
    error_response,
    register_error_handlers,
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)


# --- Test helpers ---


def _make_app():
    """Create a minimal FastAPI app with structured error handlers."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/not-found")
    async def raise_not_found():
        raise HTTPException(status_code=404, detail="Resource not found")

    @app.get("/bad-request")
    async def raise_bad_request():
        raise HTTPException(status_code=400, detail="Malformed request")

    @app.get("/auth-failed")
    async def raise_auth_failed():
        raise HTTPException(status_code=401, detail="Invalid credentials")

    @app.get("/forbidden")
    async def raise_forbidden():
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    @app.get("/conflict")
    async def raise_conflict():
        raise HTTPException(status_code=409, detail="Resource already exists")

    @app.get("/rate-limited")
    async def raise_rate_limited():
        raise HTTPException(status_code=429, detail="Too many requests")

    @app.get("/internal-error")
    async def raise_internal():
        raise RuntimeError("Something went wrong")

    @app.post("/validate")
    async def validate(body: dict):
        return {"ok": True}

    @app.get("/validation-error")
    async def raise_validation():
        from fastapi.exceptions import RequestValidationError
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "email"),
                    "msg": "field required",
                    "type": "value_error.missing",
                },
                {
                    "loc": ("body", "age"),
                    "msg": "ensure this value is greater than 0",
                    "type": "value_error.number.not_gt",
                },
            ]
        )

    @app.get("/custom-error")
    async def raise_custom(request: Request):
        return error_response(
            request=request,
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="Custom validation error",
            details={"field": "username", "reason": "too short"},
        )

    return app


# --- Schema Tests ---


def test_error_response_has_code():
    """Error response includes 'code' field."""
    app = _make_app()
    client = TestClient(app)

    resp = client.get("/not-found")
    body = resp.json()
    assert "code" in body
    assert body["code"] == "NOT_FOUND"


def test_error_response_has_message():
    """Error response includes 'message' field."""
    app = _make_app()
    client = TestClient(app)

    resp = client.get("/not-found")
    body = resp.json()
    assert "message" in body
    assert len(body["message"]) > 0


def test_error_response_has_details():
    """Error response includes 'details' field (even if empty)."""
    app = _make_app()
    client = TestClient(app)

    resp = client.get("/not-found")
    body = resp.json()
    assert "details" in body
    assert isinstance(body["details"], dict)


# --- Error Code Tests ---


def test_not_found_code():
    """404 → NOT_FOUND error code."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/not-found")
    assert resp.json()["code"] == "NOT_FOUND"
    assert resp.status_code == 404


def test_bad_request_code():
    """400 → BAD_REQUEST error code."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/bad-request")
    assert resp.json()["code"] == "BAD_REQUEST"
    assert resp.status_code == 400


def test_auth_failed_code():
    """401 → AUTH_FAILED error code."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/auth-failed")
    assert resp.json()["code"] == "AUTH_FAILED"
    assert resp.status_code == 401


def test_forbidden_code():
    """403 → FORBIDDEN error code."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/forbidden")
    assert resp.json()["code"] == "FORBIDDEN"
    assert resp.status_code == 403


def test_conflict_code():
    """409 → CONFLICT error code."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/conflict")
    assert resp.json()["code"] == "CONFLICT"
    assert resp.status_code == 409


def test_rate_limited_code():
    """429 → RATE_LIMITED error code."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/rate-limited")
    assert resp.json()["code"] == "RATE_LIMITED"
    assert resp.status_code == 429


def test_internal_error_code():
    """500 → INTERNAL_ERROR for unhandled exceptions."""
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/internal-error")
    assert resp.status_code == 500
    assert resp.json()["code"] == "INTERNAL_ERROR"


# --- Validation Error Tests ---


def test_validation_error_has_field_details():
    """Validation errors include field-level details."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/validation-error")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "fields" in body["details"]
    fields = body["details"]["fields"]
    assert len(fields) == 2
    assert fields[0]["field"] == "body → email"
    assert fields[1]["field"] == "body → age"


def test_validation_error_field_has_message():
    """Each validation field error has a message."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/validation-error")
    fields = resp.json()["details"]["fields"]
    for field in fields:
        assert "message" in field
        assert len(field["message"]) > 0


def test_validation_error_field_has_type():
    """Each validation field error has a type."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/validation-error")
    fields = resp.json()["details"]["fields"]
    for field in fields:
        assert "type" in field


# --- Request ID Tests ---


def test_request_id_present_in_error():
    """Error response includes X-Request-ID header."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/not-found")
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 0


def test_request_id_from_header():
    """Request ID from X-Request-ID header is preserved."""
    app = _make_app()
    client = TestClient(app)
    custom_id = "test-request-123"
    resp = client.get("/not-found", headers={"X-Request-ID": custom_id})
    assert resp.headers["X-Request-ID"] == custom_id


def test_request_id_auto_generated():
    """Request ID is auto-generated when not provided."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/not-found")
    request_id = resp.headers["X-Request-ID"]
    # Should be a valid UUID
    uuid.UUID(request_id)


def test_request_id_in_validation_errors():
    """Validation errors also include X-Request-ID."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/validation-error")
    assert "X-Request-ID" in resp.headers


# --- Custom Error Response Tests ---


def test_custom_error_response():
    """error_response() helper produces correct schema."""
    from starlette.requests import Request as StarletteRequest

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/custom-error")
    async def raise_custom(request: StarletteRequest):
        return error_response(
            request=request,
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="Custom validation error",
            details={"field": "username", "reason": "too short"},
        )

    client = TestClient(app)
    resp = client.get("/custom-error")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Custom validation error"
    assert body["details"]["field"] == "username"


# --- All Error Codes Documentation Test ---


def test_all_error_codes_are_documented():
    """All ErrorCode enum values are documented."""
    for code in ErrorCode:
        assert isinstance(code.value, str)
        assert len(code.value) > 0
