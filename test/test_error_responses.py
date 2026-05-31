"""Tests for structured error responses."""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_not_found_error_structure():
    """Test that 404 errors return structured response with error code."""
    response = client.get("/agents/nonexistent")

    assert response.status_code == 404
    data = response.json()

    assert "code" in data
    assert data["code"] == "NOT_FOUND"
    assert "message" in data
    assert "details" in data
    assert "request_id" in data
    assert data["details"]["agent_id"] == "nonexistent"


def test_validation_error_structure():
    """Test that validation errors include field-level details."""
    response = client.get("/agents", params={"limit": -1})

    assert response.status_code == 422
    data = response.json()

    assert data["code"] == "VALIDATION_ERROR"
    assert "fields" in data["details"]
    assert "message" in data
    assert "request_id" in data


def test_request_id_in_response():
    """Test that request_id is present in error responses."""
    response = client.get("/tasks/99999")

    assert response.status_code == 404
    data = response.json()

    assert "request_id" in data
    assert data["request_id"] is not None
    assert len(data["request_id"]) > 0


def test_request_id_header():
    """Test that X-Request-ID header is returned."""
    response = client.get("/health")

    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_custom_request_id_preserved():
    """Test that custom X-Request-ID is preserved."""
    custom_id = "test-request-123"
    response = client.get("/health", headers={"X-Request-ID": custom_id})

    assert response.headers["X-Request-ID"] == custom_id


def test_all_error_codes_documented():
    """Test that all error codes are consistent."""
    from api.models.errors import ErrorCode

    expected_codes = {
        "VALIDATION_ERROR",
        "NOT_FOUND",
        "AUTH_FAILED",
        "FORBIDDEN",
        "RATE_LIMITED",
        "INTERNAL_ERROR",
    }

    actual_codes = {
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.NOT_FOUND,
        ErrorCode.AUTH_FAILED,
        ErrorCode.FORBIDDEN,
        ErrorCode.RATE_LIMITED,
        ErrorCode.INTERNAL_ERROR,
    }

    assert actual_codes == expected_codes


def test_validation_error_field_details():
    """Test that validation errors include specific field information."""
    response = client.get("/agents", params={"limit": 200})

    if response.status_code == 422:
        data = response.json()
        assert "fields" in data["details"]

        for field_path, field_error in data["details"]["fields"].items():
            assert "message" in field_error
            assert "type" in field_error
