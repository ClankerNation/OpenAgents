"""Tests for structured error responses and custom exception handlers."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.errors import (
    ErrorCode,
    ErrorResponse,
    NotFoundException,
    AuthFailedException,
    ForbiddenException,
    RateLimitedException,
    InternalErrorException,
)


# ---------------------------------------------------------------------------
# Unit tests for error codes
# ---------------------------------------------------------------------------
class TestErrorCode:
    def test_all_codes_defined(self):
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.NOT_FOUND.value == "NOT_FOUND"
        assert ErrorCode.FORBIDDEN.value == "FORBIDDEN"
        assert ErrorCode.RATE_LIMITED.value == "RATE_LIMITED"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"


class TestErrorResponse:
    def test_basic_response(self):
        resp = ErrorResponse(code=ErrorCode.NOT_FOUND, message="Not found")
        assert resp.code == ErrorCode.NOT_FOUND
        assert resp.message == "Not found"

    def test_response_serialization(self):
        resp = ErrorResponse(
code=ErrorCode.VALIDATION_ERROR,
            message="Bad input",
            details=[{"loc": ["body"], "msg": "required", "type": "missing"}],
            request_id="req_abc",
        )
        d = resp.model_dump()
        assert d["code"] == "VALIDATION_ERROR"
        assert d["message"] == "Bad input"
        assert d["request_id"] == "req_abc"


class TestExceptions:
    def test_not_found(self):
        exc = NotFoundException("Agent", "123")
        assert exc.status_code == 404
        assert "Agent" in exc.detail

    def test_auth_failed(self):
        exc = AuthFailedException()
        assert exc.status_code == 401

    def test_forbidden(self):
        exc = ForbiddenException()
        assert exc.status_code == 403

    def test_rate_limited(self):
        exc = RateLimitedException(retry_after=120)
        assert exc.status_code == 429
        assert exc.headers["Retry-After"] == "120"

    def test_internal_error(self):
        exc = InternalErrorException()
        assert exc.status_code == 500


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------
client = TestClient(app)


class TestIntegration:
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_request_id_header(self):
        resp = client.get("/health")
        assert "x-request-id" in resp.headers

    def test_custom_request_id(self):
        resp = client.get("/health", headers={"X-Request-ID": "req_test_123"})
        assert resp.headers["x-request-id"] == "req_test_123"

    def test_not_found_request_id(self):
        resp = client.get("/agents/does_not_exist")
        assert "x-request-id" in resp.headers

    def test_error_response_has_code_field(self):
        """Error responses should include a code field."""
        resp = client.get("/agents/does_not_exist")
        data = resp.json()
        if "code" in data:
            assert isinstance(data["code"], str)
            assert len(data["code"]) > 0
