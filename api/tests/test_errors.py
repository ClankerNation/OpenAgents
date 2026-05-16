"""Tests for structured error handling in the OpenAgents API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ..errors import (
    ErrorCode,
    APIError,
    NotFoundError,
    AuthenticationError,
    ForbiddenError,
    RateLimitError,
    ValidationError,
    ConflictError,
    register_error_handlers,
    build_error_response,
)


# Test app setup
app = FastAPI()
register_error_handlers(app)


class TestInput(BaseModel):
    name: str
    count: int


@app.get("/not-found")
async def trigger_not_found():
    raise NotFoundError("Agent", 123)


@app.get("/auth-failed")
async def trigger_auth_failed():
    raise AuthenticationError("Token has expired")


@app.get("/forbidden")
async def trigger_forbidden():
    raise ForbiddenError("You don't have access")


@app.get("/rate-limited")
async def trigger_rate_limited():
    raise RateLimitError(retry_after=60)


@app.get("/validation-error")
async def trigger_validation_error():
    raise ValidationError("Invalid input", {"email": "Invalid email format"})


@app.get("/conflict")
async def trigger_conflict():
    raise ConflictError("Resource already exists")


@app.get("/internal-error")
async def trigger_internal_error():
    raise Exception("Something went wrong")


@app.post("/pydantic-validation")
async def trigger_pydantic_validation(data: TestInput):
    return data


client = TestClient(app)


class TestErrorCodes:
    """Test that all error codes are properly defined."""

    def test_error_codes_exist(self):
        assert ErrorCode.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCode.NOT_FOUND == "NOT_FOUND"
        assert ErrorCode.AUTH_FAILED == "AUTH_FAILED"
        assert ErrorCode.FORBIDDEN == "FORBIDDEN"
        assert ErrorCode.RATE_LIMITED == "RATE_LIMITED"
        assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"
        assert ErrorCode.BAD_REQUEST == "BAD_REQUEST"
        assert ErrorCode.CONFLICT == "CONFLICT"


class TestNotFoundError:
    """Test NOT_FOUND error responses."""

    def test_not_found_response_structure(self):
        response = client.get("/not-found")
        assert response.status_code == 404

        data = response.json()
        assert data["code"] == "NOT_FOUND"
        assert data["message"] == "Agent not found"
        assert "request_id" in data
        assert data["details"]["resource"] == "Agent"
        assert data["details"]["identifier"] == "123"

    def test_not_found_has_request_id_header(self):
        response = client.get("/not-found")
        assert "X-Request-ID" in response.headers


class TestAuthenticationError:
    """Test AUTH_FAILED error responses."""

    def test_auth_failed_response_structure(self):
        response = client.get("/auth-failed")
        assert response.status_code == 401

        data = response.json()
        assert data["code"] == "AUTH_FAILED"
        assert data["message"] == "Token has expired"
        assert "request_id" in data


class TestForbiddenError:
    """Test FORBIDDEN error responses."""

    def test_forbidden_response_structure(self):
        response = client.get("/forbidden")
        assert response.status_code == 403

        data = response.json()
        assert data["code"] == "FORBIDDEN"
        assert data["message"] == "You don't have access"
        assert "request_id" in data


class TestRateLimitError:
    """Test RATE_LIMITED error responses."""

    def test_rate_limited_response_structure(self):
        response = client.get("/rate-limited")
        assert response.status_code == 429

        data = response.json()
        assert data["code"] == "RATE_LIMITED"
        assert data["message"] == "Rate limit exceeded"
        assert data["details"]["retry_after"] == 60
        assert "request_id" in data


class TestValidationError:
    """Test VALIDATION_ERROR responses."""

    def test_custom_validation_error(self):
        response = client.get("/validation-error")
        assert response.status_code == 422

        data = response.json()
        assert data["code"] == "VALIDATION_ERROR"
        assert data["message"] == "Invalid input"
        assert data["details"]["fields"]["email"] == "Invalid email format"

    def test_pydantic_validation_error(self):
        response = client.post("/pydantic-validation", json={"name": 123})
        assert response.status_code == 422

        data = response.json()
        assert data["code"] == "VALIDATION_ERROR"
        assert data["message"] == "Request validation failed"
        assert "fields" in data["details"]
        assert "request_id" in data


class TestConflictError:
    """Test CONFLICT error responses."""

    def test_conflict_response_structure(self):
        response = client.get("/conflict")
        assert response.status_code == 409

        data = response.json()
        assert data["code"] == "CONFLICT"
        assert data["message"] == "Resource already exists"
        assert "request_id" in data


class TestInternalError:
    """Test INTERNAL_ERROR responses."""

    def test_internal_error_response_structure(self):
        response = client.get("/internal-error")
        assert response.status_code == 500

        data = response.json()
        assert data["code"] == "INTERNAL_ERROR"
        assert data["message"] == "An internal error occurred"
        assert "request_id" in data


class TestRequestIdPropagation:
    """Test that request IDs are properly propagated."""

    def test_custom_request_id_used(self):
        custom_id = "test-request-id-12345"
        response = client.get("/not-found", headers={"X-Request-ID": custom_id})

        data = response.json()
        assert data["request_id"] == custom_id
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_generated_if_missing(self):
        response = client.get("/not-found")
        data = response.json()
        assert "request_id" in data
        assert len(data["request_id"]) == 36  # UUID format


class TestBuildErrorResponse:
    """Test the build_error_response helper."""

    def test_builds_complete_response(self):
        response = build_error_response(
            code=ErrorCode.NOT_FOUND,
            message="Resource not found",
            request_id="abc-123",
            details={"id": 42},
        )
        assert response["code"] == "NOT_FOUND"
        assert response["message"] == "Resource not found"
        assert response["request_id"] == "abc-123"
        assert response["details"]["id"] == 42

    def test_omits_details_when_none(self):
        response = build_error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message="Error",
            request_id="abc-123",
        )
        assert "details" not in response
