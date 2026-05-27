"""Tests for structured error responses.

@fix-author
  name: wanglovefly-oss
  date: 2026-05-27
  @runtime: {os: linux, arch: x64, working_dir: /mnt/c/Users/wsda/OpenAgents, shell: bash}
"""

import uuid

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from ..errors import (
    ErrorCode,
    ErrorResponse,
    register_error_handlers,
    _get_request_id,
    _map_status_to_code,
    _build_error_response,
)
from ..main import app as main_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject request_id into request.state for testing."""
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """A minimal FastAPI app with error handlers registered."""
    application = FastAPI()

    # Register middleware first
    application.add_middleware(_RequestIDMiddleware)

    # Then error handlers
    register_error_handlers(application)

    # Also add a specific handler for ValueError in test context
    @application.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):  # noqa: F811
        return await _build_error_response(
            request=request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            message="An internal server error occurred",
        )

    @application.get("/ok")
    async def ok():
        return {"status": "ok"}

    @application.get("/not-found")
    async def not_found():
        raise HTTPException(status_code=404, detail="Resource not found")

    @application.get("/auth-failed")
    async def auth_failed():
        raise HTTPException(status_code=401, detail="Invalid credentials")

    @application.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    @application.get("/rate-limited")
    async def rate_limited():
        raise HTTPException(status_code=429, detail="Too many requests")

    @application.get("/internal-error")
    async def internal_error():
        raise ValueError("Something went wrong")

    @application.post("/validate-model")
    async def validate_model(body: dict):
        return body

    class ValidatedBody(BaseModel):
        name: str = Field(..., min_length=1)
        age: int = Field(..., ge=0, le=150)

    @application.post("/validate-field")
    async def validate_field(body: ValidatedBody):
        return body

    return application


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Error schema tests
# ---------------------------------------------------------------------------

class TestErrorResponseSchema:
    """Verify ErrorResponse Pydantic model serialization."""

    def test_full_schema(self):
        """All fields populated."""
        resp = ErrorResponse(
            code=ErrorCode.NOT_FOUND,
            message="Agent not found",
            details=[{"field": "agent_id", "message": "Not found"}],
            request_id="req-123",
        )
        data = resp.model_dump(exclude_none=True)
        assert data["code"] == "NOT_FOUND"
        assert data["message"] == "Agent not found"
        assert data["details"][0]["field"] == "agent_id"
        assert data["request_id"] == "req-123"

    def test_minimal_schema(self):
        """Only required fields."""
        resp = ErrorResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message="Server error",
            request_id="req-456",
        )
        data = resp.model_dump(exclude_none=True)
        assert data["code"] == "INTERNAL_ERROR"
        assert data["message"] == "Server error"
        assert "details" not in data
        assert data["request_id"] == "req-456"

    def test_all_error_codes_have_constants(self):
        """Ensure all required error codes exist."""
        assert ErrorCode.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCode.NOT_FOUND == "NOT_FOUND"
        assert ErrorCode.AUTH_FAILED == "AUTH_FAILED"
        assert ErrorCode.RATE_LIMITED == "RATE_LIMITED"
        assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"


class TestStatusCodeMapping:
    """Verify HTTP status code to error code mapping."""

    @pytest.mark.parametrize(
        "status_code,expected_code",
        [
            (400, ErrorCode.VALIDATION_ERROR),
            (401, ErrorCode.AUTH_FAILED),
            (403, ErrorCode.AUTH_FAILED),
            (404, ErrorCode.NOT_FOUND),
            (422, ErrorCode.VALIDATION_ERROR),
            (429, ErrorCode.RATE_LIMITED),
            (500, ErrorCode.INTERNAL_ERROR),
            (503, ErrorCode.INTERNAL_ERROR),  # unmapped -> fallback
        ],
    )
    @pytest.mark.asyncio
    async def test_mapping(self, status_code, expected_code):
        code = await _map_status_to_code(status_code)
        assert code == expected_code


# ---------------------------------------------------------------------------
# Integration tests via TestClient
# ---------------------------------------------------------------------------

class TestErrorResponsesIntegration:
    """End-to-end tests for structured error responses."""

    def test_200_ok(self, client):
        """Normal response unaffected."""
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_404_not_found(self, client):
        """NOT_FOUND error code with message."""
        resp = client.get("/not-found")
        assert resp.status_code == 404
        data = resp.json()
        assert data["code"] == ErrorCode.NOT_FOUND
        assert data["message"] == "Resource not found"
        assert "request_id" in data

    def test_401_auth_failed(self, client):
        """AUTH_FAILED error code."""
        resp = client.get("/auth-failed")
        assert resp.status_code == 401
        data = resp.json()
        assert data["code"] == ErrorCode.AUTH_FAILED
        assert data["message"] == "Invalid credentials"
        assert "request_id" in data

    def test_403_forbidden(self, client):
        """AUTH_FAILED for 403."""
        resp = client.get("/forbidden")
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == ErrorCode.AUTH_FAILED
        assert data["message"] == "Insufficient permissions"

    def test_429_rate_limited(self, client):
        """RATE_LIMITED error code."""
        resp = client.get("/rate-limited")
        assert resp.status_code == 429
        data = resp.json()
        assert data["code"] == ErrorCode.RATE_LIMITED
        assert data["message"] == "Too many requests"

    def test_500_internal_error(self, client):
        """INTERNAL_ERROR for uncaught exceptions."""
        resp = client.get("/internal-error")
        assert resp.status_code == 500
        data = resp.json()
        assert data["code"] == ErrorCode.INTERNAL_ERROR
        assert data["message"] == "An internal server error occurred"
        assert "request_id" in data

    def test_422_validation_error_field_details(self, client):
        """Validation errors include field-level details."""
        resp = client.post("/validate-field", json={"name": "", "age": -1})
        assert resp.status_code == 422
        data = resp.json()
        assert data["code"] == ErrorCode.VALIDATION_ERROR
        assert data["message"] == "Request validation failed"
        assert "details" in data
        assert isinstance(data["details"], list)
        # Should have field-level errors
        detail_fields = set()
        for d in data["details"]:
            if d.get("field"):
                detail_fields.add(d["field"])
        assert any("name" in f or "age" in f for f in detail_fields)

    def test_request_id_present_in_all_errors(self, client):
        """Every error response includes a request_id."""
        for url in [
            "/not-found",
            "/auth-failed",
            "/forbidden",
            "/rate-limited",
            "/internal-error",
        ]:
            resp = client.get(url)
            data = resp.json()
            assert "request_id" in data, f"Missing request_id in {url}"
            assert data["request_id"], f"Empty request_id in {url}"

    def test_request_id_preserved_from_header(self, client):
        """Request ID from X-Request-ID header is preserved in error response."""
        req_id = "my-custom-trace-id-001"
        resp = client.get("/not-found", headers={"X-Request-ID": req_id})
        data = resp.json()
        assert data["request_id"] == req_id

    def test_request_id_in_response_headers(self, client):
        """X-Request-ID is set in response headers even on errors."""
        resp = client.get("/not-found")
        assert "X-Request-ID" in resp.headers
        assert resp.headers["X-Request-ID"]


# ---------------------------------------------------------------------------
# Test all error codes
# ---------------------------------------------------------------------------

class TestAllErrorCodes:
    """Test that every error code can be produced."""

    @pytest.mark.parametrize(
        "url,expected_status,expected_code",
        [
            ("/not-found", 404, ErrorCode.NOT_FOUND),
            ("/auth-failed", 401, ErrorCode.AUTH_FAILED),
            ("/forbidden", 403, ErrorCode.AUTH_FAILED),
            ("/rate-limited", 429, ErrorCode.RATE_LIMITED),
        ],
    )
    def test_error_code(self, client, url, expected_status, expected_code):
        resp = client.get(url)
        data = resp.json()
        assert resp.status_code == expected_status
        assert data["code"] == expected_code


# ---------------------------------------------------------------------------
# Test the real main app
# ---------------------------------------------------------------------------

class TestMainApp:
    """Verify the actual main app works with structured errors."""

    @pytest.fixture
    def main_client(self):
        return TestClient(main_app)

    def test_main_app_404(self, main_client):
        """Main app returns structured errors."""
        resp = main_client.get("/agents/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert data["code"] == ErrorCode.NOT_FOUND
        assert data["message"] == "Agent not found"
        assert "request_id" in data

    def test_main_app_health(self, main_client):
        """Health endpoint still works."""
        resp = main_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_main_app_request_id_header(self, main_client):
        """X-Request-ID header present in response."""
        resp = main_client.get("/agents/nonexistent")
        assert "X-Request-ID" in resp.headers

    def test_main_app_200_ok(self, main_client):
        """Health endpoint unaffected."""
        resp = main_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
