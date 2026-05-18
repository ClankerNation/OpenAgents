"""
@contributor: hermes-agent
@platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
@env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
@timestamp: 2026-05-18
"""

"""Tests for structured error responses across all API endpoints.

Validates that every error scenario returns a response matching the schema:
{code: str, message: str, details: dict, request_id: str}
with consistent error codes: VALIDATION_ERROR, NOT_FOUND, AUTH_FAILED,
RATE_LIMITED, INTERNAL_ERROR.
"""

import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Import the error framework
# ---------------------------------------------------------------------------

from api.middleware.errors import (
    AppError,
    NotFoundError,
    AuthFailedError,
    ForbiddenError,
    ValidationError,
    BadRequestError,
    RateLimitedError,
    InternalError,
    ErrorCode,
    ErrorResponse,
    register_error_handlers,
)


# ---------------------------------------------------------------------------
# Models (named ValidationTestModel to avoid pytest collection warning)
# ---------------------------------------------------------------------------

class ValidationTestModel(BaseModel):
    name: str
    age: int


# ---------------------------------------------------------------------------
# Fixtures — create a minimal FastAPI app for testing
# ---------------------------------------------------------------------------

def create_test_app() -> FastAPI:
    """Create a FastAPI test application with error handlers and sample routes."""
    app = FastAPI()
    register_error_handlers(app)

    # --- Route definitions that exercise all error types ---

    @app.get("/test/not-found")
    async def raise_not_found():
        raise NotFoundError("Item not found")

    @app.get("/test/not-found-with-details")
    async def raise_not_found_with_details():
        raise NotFoundError("Agent not found", details={"agent_id": "abc-123"})

    @app.get("/test/auth-failed")
    async def raise_auth_failed():
        raise AuthFailedError("Token expired")

    @app.get("/test/auth-failed-invalid")
    async def raise_auth_failed_invalid():
        raise AuthFailedError("Invalid token", details={"reason": "malformed_jwt"})

    @app.get("/test/forbidden")
    async def raise_forbidden():
        raise ForbiddenError("Not the owner")

    @app.get("/test/validation-error")
    async def raise_validation_error():
        raise ValidationError("Missing required field", details={"field": "name"})

    @app.get("/test/bad-request")
    async def raise_bad_request():
        raise BadRequestError("Cannot cancel an active task")

    @app.get("/test/rate-limited")
    async def raise_rate_limited():
        raise RateLimitedError("Too many requests", details={"retry_after": 60})

    @app.get("/test/internal-error")
    async def raise_internal_error():
        raise InternalError("Database connection failed")

    @app.get("/test/http-404")
    async def raise_http_404():
        raise HTTPException(status_code=404, detail="Not found via HTTPException")

    @app.get("/test/http-401")
    async def raise_http_401():
        raise HTTPException(status_code=401, detail="Unauthorized via HTTPException")

    @app.get("/test/http-403")
    async def raise_http_403():
        raise HTTPException(status_code=403, detail="Forbidden via HTTPException")

    @app.get("/test/http-400")
    async def raise_http_400():
        raise HTTPException(status_code=400, detail="Bad request via HTTPException")

    @app.get("/test/http-429")
    async def raise_http_429():
        raise HTTPException(status_code=429, detail="Too many requests")

    @app.get("/test/http-500")
    async def raise_http_500():
        raise HTTPException(status_code=500, detail="Something went wrong")

    @app.post("/test/validation-pydantic")
    async def validation_endpoint(body: ValidationTestModel):
        return {"received": body.name}

    @app.get("/test/unhandled-exception")
    async def raise_unhandled():
        raise RuntimeError("Unexpected crash")

    @app.get("/test/success")
    async def success_endpoint():
        return {"status": "ok"}

    return app


@pytest.fixture
def client():
    app = create_test_app()
    # raise_server_exceptions=False allows our Exception handler to run
    # instead of Starlette's ServerErrorMiddleware re-raising
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Test: ErrorResponse class
# ---------------------------------------------------------------------------

class TestErrorResponse:
    """Unit tests for the ErrorResponse model."""

    def test_default_request_id_is_uuid(self):
        resp = ErrorResponse(code="TEST", message="hello")
        assert resp.request_id is not None
        # UUID v4 format validation
        import uuid
        uuid.UUID(resp.request_id)  # will raise if invalid

    def test_custom_request_id(self):
        resp = ErrorResponse(code="TEST", message="hello", request_id="custom-123")
        assert resp.request_id == "custom-123"

    def test_to_dict_structure(self):
        resp = ErrorResponse(code="NOT_FOUND", message="Item missing", details={"id": 42}, request_id="req-1")
        d = resp.to_dict()
        assert d == {
            "code": "NOT_FOUND",
            "message": "Item missing",
            "details": {"id": 42},
            "request_id": "req-1",
        }

    def test_to_dict_defaults_empty_details(self):
        resp = ErrorResponse(code="TEST", message="hi")
        d = resp.to_dict()
        assert d["details"] == {}
        assert "request_id" in d

    def test_to_json_response(self):
        resp = ErrorResponse(code="NOT_FOUND", message="not here", request_id="r1")
        json_resp = resp.to_json_response(404)
        assert json_resp.status_code == 404
        # Starlette JSONResponse body is accessible via .body
        import json
        body = json.loads(json_resp.body)
        assert body["code"] == "NOT_FOUND"
        assert body["request_id"] == "r1"


# ---------------------------------------------------------------------------
# Test: ErrorCode constants
# ---------------------------------------------------------------------------

class TestErrorCode:
    def test_all_required_codes_exist(self):
        assert ErrorCode.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCode.NOT_FOUND == "NOT_FOUND"
        assert ErrorCode.AUTH_FAILED == "AUTH_FAILED"
        assert ErrorCode.RATE_LIMITED == "RATE_LIMITED"
        assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"
        assert ErrorCode.FORBIDDEN == "FORBIDDEN"
        assert ErrorCode.BAD_REQUEST == "BAD_REQUEST"


# ---------------------------------------------------------------------------
# Test: Custom exception classes
# ---------------------------------------------------------------------------

class TestCustomExceptions:
    def test_not_found_error(self):
        err = NotFoundError("Resource gone")
        assert err.code == ErrorCode.NOT_FOUND
        assert err.message == "Resource gone"
        assert err.status_code == 404

    def test_not_found_error_default(self):
        err = NotFoundError()
        assert err.message == "Resource not found"
        assert err.status_code == 404

    def test_auth_failed_error(self):
        err = AuthFailedError("Bad token")
        assert err.code == ErrorCode.AUTH_FAILED
        assert err.status_code == 401

    def test_auth_failed_error_default(self):
        err = AuthFailedError()
        assert err.message == "Authentication failed"

    def test_forbidden_error(self):
        err = ForbiddenError("No access")
        assert err.code == ErrorCode.FORBIDDEN
        assert err.status_code == 403

    def test_validation_error(self):
        err = ValidationError("Bad input")
        assert err.code == ErrorCode.VALIDATION_ERROR
        assert err.status_code == 422

    def test_bad_request_error(self):
        err = BadRequestError("Invalid state")
        assert err.code == ErrorCode.BAD_REQUEST
        assert err.status_code == 400

    def test_rate_limited_error(self):
        err = RateLimitedError("Slow down")
        assert err.code == ErrorCode.RATE_LIMITED
        assert err.status_code == 429

    def test_internal_error(self):
        err = InternalError("DB down")
        assert err.code == ErrorCode.INTERNAL_ERROR
        assert err.status_code == 500

    def test_app_error_with_details(self):
        err = NotFoundError("Agent missing", details={"agent_id": "a1"})
        assert err.details == {"agent_id": "a1"}

    def test_app_error_is_exception(self):
        err = NotFoundError("test")
        assert isinstance(err, Exception)

    def test_app_error_default_details(self):
        err = NotFoundError("test")
        assert err.details == {}


# ---------------------------------------------------------------------------
# Test: API endpoints with structured error responses
# ---------------------------------------------------------------------------

class TestAPINotFoundErrors:
    def test_not_found_error(self, client):
        resp = client.get("/test/not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "NOT_FOUND"
        assert body["message"] == "Item not found"
        assert "request_id" in body
        assert isinstance(body["details"], dict)

    def test_not_found_with_details(self, client):
        resp = client.get("/test/not-found-with-details")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "NOT_FOUND"
        assert body["details"] == {"agent_id": "abc-123"}

    def test_http_404_exception(self, client):
        resp = client.get("/test/http-404")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "NOT_FOUND"
        assert "request_id" in body
        assert body["message"] == "Not found via HTTPException"


class TestAPIAuthErrors:
    def test_auth_failed_error(self, client):
        resp = client.get("/test/auth-failed")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "AUTH_FAILED"
        assert body["message"] == "Token expired"
        assert "request_id" in body

    def test_auth_failed_with_details(self, client):
        resp = client.get("/test/auth-failed-invalid")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "AUTH_FAILED"
        assert body["details"] == {"reason": "malformed_jwt"}

    def test_http_401_exception(self, client):
        resp = client.get("/test/http-401")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "AUTH_FAILED"


class TestAPIForbiddenErrors:
    def test_forbidden_error(self, client):
        resp = client.get("/test/forbidden")
        assert resp.status_code == 403
        body = resp.json()
        assert body["code"] == "FORBIDDEN"
        assert body["message"] == "Not the owner"

    def test_http_403_exception(self, client):
        resp = client.get("/test/http-403")
        assert resp.status_code == 403
        body = resp.json()
        assert body["code"] == "FORBIDDEN"


class TestAPIValidationErrors:
    def test_validation_error(self, client):
        resp = client.get("/test/validation-error")
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert body["message"] == "Missing required field"
        assert body["details"] == {"field": "name"}

    def test_pydantic_validation_error(self, client):
        """Pydantic request model validation errors should use VALIDATION_ERROR code."""
        resp = client.post("/test/validation-pydantic", json={"name": 123, "age": "not_int"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "request_id" in body
        assert "fields" in body["details"]
        assert len(body["details"]["fields"]) > 0

    def test_pydantic_validation_missing_required_field(self, client):
        """Missing required fields should return VALIDATION_ERROR with field details."""
        resp = client.post("/test/validation-pydantic", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "fields" in body["details"]

    def test_pydantic_validation_wrong_type(self, client):
        resp = client.post("/test/validation-pydantic", json={"name": "Alice", "age": "twenty"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        fields = body["details"]["fields"]
        # Should have error for age field type mismatch
        assert any("age" in str(f.get("loc", [])) for f in fields)


class TestAPIBadRequestErrors:
    def test_bad_request_error(self, client):
        resp = client.get("/test/bad-request")
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "BAD_REQUEST"
        assert body["message"] == "Cannot cancel an active task"

    def test_http_400_exception(self, client):
        resp = client.get("/test/http-400")
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "BAD_REQUEST"


class TestAPIRateLimitedErrors:
    def test_rate_limited_error(self, client):
        resp = client.get("/test/rate-limited")
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == "RATE_LIMITED"
        assert body["details"] == {"retry_after": 60}

    def test_http_429_exception(self, client):
        resp = client.get("/test/http-429")
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == "RATE_LIMITED"


class TestAPIInternalErrors:
    def test_internal_error(self, client):
        resp = client.get("/test/internal-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "INTERNAL_ERROR"
        assert "request_id" in body

    def test_http_500_exception(self, client):
        resp = client.get("/test/http-500")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "INTERNAL_ERROR"

    def test_unhandled_exception(self, client):
        """Unhandled exceptions should be caught by the generic handler."""
        resp = client.get("/test/unhandled-exception")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "INTERNAL_ERROR"
        assert body["message"] == "An unexpected error occurred"
        assert "request_id" in body


# ---------------------------------------------------------------------------
# Test: request_id propagation
# ---------------------------------------------------------------------------

class TestRequestId:
    def test_request_id_in_all_responses(self, client):
        """Every error response must include a request_id."""
        endpoints = [
            "/test/not-found",
            "/test/auth-failed",
            "/test/forbidden",
            "/test/validation-error",
            "/test/bad-request",
            "/test/rate-limited",
            "/test/internal-error",
            "/test/http-404",
            "/test/http-500",
        ]
        for path in endpoints:
            resp = client.get(path)
            body = resp.json()
            assert "request_id" in body, f"Missing request_id in response from {path}"
            # request_id should be a non-empty string
            assert len(body["request_id"]) > 0, f"Empty request_id from {path}"

    def test_custom_request_id_from_header(self, client):
        """X-Request-ID header should be echoed back in the response."""
        resp = client.get("/test/not-found", headers={"X-Request-ID": "my-custom-req-42"})
        body = resp.json()
        assert body["request_id"] == "my-custom-req-42"

    def test_custom_request_id_auth_failed(self, client):
        resp = client.get("/test/auth-failed", headers={"X-Request-ID": "auth-req-99"})
        body = resp.json()
        assert body["request_id"] == "auth-req-99"

    def test_custom_request_id_validation(self, client):
        resp = client.post("/test/validation-pydantic", json={}, headers={"X-Request-ID": "val-req-7"})
        body = resp.json()
        assert body["request_id"] == "val-req-7"

    def test_custom_request_id_on_http_exception(self, client):
        resp = client.get("/test/http-403", headers={"X-Request-ID": "http-req-1"})
        body = resp.json()
        assert body["request_id"] == "http-req-1"


# ---------------------------------------------------------------------------
# Test: Success endpoint is not affected by error handler
# ---------------------------------------------------------------------------

class TestSuccessEndpoint:
    def test_success_still_works(self, client):
        resp = client.get("/test/success")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Test: Schema consistency — every error has the required 4 fields
# ---------------------------------------------------------------------------

class TestSchemaConsistency:
    def test_all_errors_have_required_fields(self, client):
        """Every error response must contain code, message, details, and request_id."""
        endpoints = [
            ("/test/not-found", 404),
            ("/test/auth-failed", 401),
            ("/test/forbidden", 403),
            ("/test/validation-error", 422),
            ("/test/bad-request", 400),
            ("/test/rate-limited", 429),
            ("/test/internal-error", 500),
            ("/test/http-404", 404),
            ("/test/http-401", 401),
            ("/test/http-403", 403),
            ("/test/http-400", 400),
            ("/test/http-429", 429),
            ("/test/http-500", 500),
        ]
        for path, expected_status in endpoints:
            resp = client.get(path)
            assert resp.status_code == expected_status, f"Wrong status for {path}"
            body = resp.json()
            assert "code" in body, f"Missing 'code' in response from {path}"
            assert "message" in body, f"Missing 'message' in response from {path}"
            assert "details" in body, f"Missing 'details' in response from {path}"
            assert "request_id" in body, f"Missing 'request_id' in response from {path}"
            assert isinstance(body["code"], str), f"'code' is not a string from {path}"
            assert isinstance(body["message"], str), f"'message' is not a string from {path}"
            assert isinstance(body["details"], dict), f"'details' is not a dict from {path}"
            assert isinstance(body["request_id"], str), f"'request_id' is not a string from {path}"

    def test_unhandled_exception_has_required_fields(self, client):
        """Test unhandled exception schema separately due to Starlette middleware."""
        resp = client.get("/test/unhandled-exception")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "INTERNAL_ERROR"
        assert "message" in body
        assert "details" in body
        assert "request_id" in body

    def test_pydantic_error_has_required_fields(self, client):
        """Pydantic validation errors should also have the full schema."""
        resp = client.post("/test/validation-pydantic", json={"name": 123})
        assert resp.status_code == 422
        body = resp.json()
        assert "code" in body
        assert "message" in body
        assert "details" in body
        assert "request_id" in body
        assert body["code"] == "VALIDATION_ERROR"