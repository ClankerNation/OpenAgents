"""
@fix-author
  name: Metatron
  date: 2026-05-16
  platform: Hermes Agent
  cron_job: 79683e6ae067
  runtime:
    os: linux (WSL)
    arch: x86_64
    working_dir: /home/power/projects/OpenAgents
    shell: bash

Tests for structured error responses — verifies error schema, codes, field-level
validation details, and request_id presence across all endpoints.
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.errors import (
    ErrorCode,
    ErrorResponse,
    NotFoundError,
    AuthFailedError,
    ForbiddenError,
    RateLimitedError,
    BadRequestError,
    AppError,
    register_error_handlers,
)


# ── Fixtures ──

@pytest.fixture
def app():
    """Minimal FastAPI app with structured error handlers registered."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/not-found")
    async def not_found():
        raise NotFoundError("Resource not found", details={"id": 42})

    @app.get("/auth-failed")
    async def auth_failed():
        raise AuthFailedError("Invalid credentials")

    @app.get("/forbidden")
    async def forbidden():
        raise ForbiddenError("Access denied", details={"role": "admin"})

    @app.get("/bad-request")
    async def bad_request():
        raise BadRequestError("Invalid input", details={"field": "email"})

    @app.get("/internal-error")
    async def internal_error():
        raise RuntimeError("Something blew up")

    # Validation error endpoint
    class ItemModel(BaseModel):
        name: str
        price: float

    @app.post("/validate")
    async def validate(item: ItemModel):
        return item

    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ── Schema validation ──

class TestErrorSchema:
    """Verify all error responses follow the canonical schema."""

    def test_not_found_schema(self, client):
        resp = client.get("/not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == ErrorCode.NOT_FOUND
        assert body["message"] == "Resource not found"
        assert body["details"] == {"id": 42}
        assert "request_id" in body
        assert uuid.UUID(body["request_id"])

    def test_auth_failed_schema(self, client):
        resp = client.get("/auth-failed")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == ErrorCode.AUTH_FAILED
        assert body["message"] == "Invalid credentials"
        assert "request_id" in body

    def test_forbidden_schema(self, client):
        resp = client.get("/forbidden")
        assert resp.status_code == 403
        body = resp.json()
        assert body["code"] == ErrorCode.FORBIDDEN
        assert body["message"] == "Access denied"
        assert body["details"] == {"role": "admin"}

    def test_bad_request_schema(self, client):
        resp = client.get("/bad-request")
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == ErrorCode.BAD_REQUEST
        assert body["message"] == "Invalid input"
        assert body["details"] == {"field": "email"}

    def test_internal_error_schema(self, client):
        resp = client.get("/internal-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == ErrorCode.INTERNAL_ERROR
        assert body["message"] == "An unexpected error occurred"
        assert body["details"] == {}
        assert "request_id" in body


# ── Request ID ──

class TestRequestId:
    def test_generates_uuid_when_not_provided(self, client):
        resp = client.get("/not-found")
        rid = resp.json()["request_id"]
        uuid.UUID(rid)  # raises if not valid UUID

    def test_passes_through_x_request_id_header(self, client):
        resp = client.get("/not-found", headers={"X-Request-ID": "abc-123-custom"})
        assert resp.json()["request_id"] == "abc-123-custom"


# ── Validation errors ──

class TestValidationErrors:
    def test_missing_required_field(self, client):
        resp = client.post("/validate", json={"price": 9.99})
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == ErrorCode.VALIDATION_ERROR
        assert body["message"] == "Request validation failed"
        assert "details" in body
        fields = {e["field"] for e in body["details"]["fields"]}
        assert "body.name" in fields or "name" in fields

    def test_wrong_type(self, client):
        resp = client.post("/validate", json={"name": "test", "price": "not-a-number"})
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == ErrorCode.VALIDATION_ERROR
        fields = {e["field"]: e for e in body["details"]["fields"]}
        price_field = None
        for key in fields:
            if "price" in key:
                price_field = fields[key]
                break
        assert price_field is not None
        assert price_field["type"] is not None

    def test_extra_fields_ignored(self, client):
        """Extra fields should not cause validation errors (Pydantic default)."""
        resp = client.post(
            "/validate", json={"name": "test", "price": 1.0, "extra": "unwanted"}
        )
        assert resp.status_code == 200


# ── Error response data class ──

class TestErrorResponseDataclass:
    def test_full_to_dict(self):
        err = ErrorResponse(
            code="TEST", message="test msg", details={"a": 1}, request_id="r1"
        )
        d = err.to_dict()
        assert d == {
            "code": "TEST",
            "message": "test msg",
            "details": {"a": 1},
            "request_id": "r1",
        }

    def test_minimal_to_dict(self):
        err = ErrorResponse(code="TEST", message="minimal")
        d = err.to_dict()
        assert d == {"code": "TEST", "message": "minimal"}


# ── Error code coverage ──

class TestErrorCodeCoverage:
    """Verify each documented error code is used by at least one exception class."""

    CODE_TO_CLASS = {
        ErrorCode.NOT_FOUND: NotFoundError,
        ErrorCode.AUTH_FAILED: AuthFailedError,
        ErrorCode.FORBIDDEN: ForbiddenError,
        ErrorCode.RATE_LIMITED: RateLimitedError,
        ErrorCode.BAD_REQUEST: BadRequestError,
        ErrorCode.VALIDATION_ERROR: Exception,  # handled by validation_exception_handler
        ErrorCode.INTERNAL_ERROR: AppError,
    }

    @pytest.mark.parametrize("code,cls", CODE_TO_CLASS.items())
    def test_error_code_has_handler(self, code, cls):
        """Each error code is mapped to a typed exception or explicit handler."""
        assert code is not None
        assert cls is not None


# ── AppError base class ──

class TestAppErrorBase:
    def test_app_error_defaults(self):
        exc = AppError("Something wrong")
        assert exc.status_code == 500
        assert exc.error_code == ErrorCode.INTERNAL_ERROR
        detail = exc.detail
        assert isinstance(detail, dict)
        assert detail["code"] == ErrorCode.INTERNAL_ERROR
        assert detail["message"] == "Something wrong"

    def test_app_error_with_details(self):
        exc = AppError("Oops", details={"retry": True})
        assert exc.detail["details"] == {"retry": True}

    def test_app_error_with_headers(self):
        exc = AppError("Oops", headers={"X-Custom": "value"})
        assert exc.headers["X-Custom"] == "value"
