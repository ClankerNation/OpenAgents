"""Tests for structured error responses."""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.models.errors import ErrorCode

client = TestClient(app)


def test_not_found_error():
    """Test NOT_FOUND error code for missing resources."""
    response = client.get("/agents/nonexistent-agent-id")
    assert response.status_code == 404

    data = response.json()
    assert data["code"] == ErrorCode.NOT_FOUND
    assert "message" in data
    assert "request_id" in data
    assert data["request_id"] is not None


def test_validation_error_with_field_details():
    """Test VALIDATION_ERROR with field-level details."""
    # Send invalid query parameter (negative limit)
    response = client.get("/agents?limit=-5")
    assert response.status_code == 422

    data = response.json()
    assert data["code"] == ErrorCode.VALIDATION_ERROR
    assert data["message"] == "Request validation failed"
    assert "details" in data
    assert "validation_errors" in data["details"]
    assert len(data["details"]["validation_errors"]) > 0
    assert "request_id" in data


def test_validation_error_structure():
    """Test validation error includes field, message, and type."""
    response = client.get("/agents?limit=invalid")
    assert response.status_code == 422

    data = response.json()
    errors = data["details"]["validation_errors"]

    for error in errors:
        assert "field" in error
        assert "message" in error
        assert "type" in error


def test_task_not_found_error():
    """Test NOT_FOUND error for missing task."""
    response = client.get("/tasks/99999")
    assert response.status_code == 404

    data = response.json()
    assert data["code"] == ErrorCode.NOT_FOUND
    assert "request_id" in data


def test_error_response_schema():
    """Test all error responses follow the standard schema."""
    # Test various error scenarios
    test_cases = [
        ("/agents/missing", 404),
        ("/tasks/999999", 404),
        ("/agents?limit=abc", 422),
    ]

    for endpoint, expected_status in test_cases:
        response = client.get(endpoint)
        assert response.status_code == expected_status

        data = response.json()
        # Verify schema
        assert "code" in data
        assert "message" in data
        assert "request_id" in data
        assert isinstance(data["code"], str)
        assert isinstance(data["message"], str)
        assert isinstance(data["request_id"], str)


def test_request_id_uniqueness():
    """Test that each error response has a unique request_id."""
    request_ids = set()

    for _ in range(5):
        response = client.get("/agents/nonexistent")
        data = response.json()
        request_id = data["request_id"]
        assert request_id not in request_ids
        request_ids.add(request_id)


def test_health_endpoint_still_works():
    """Test that health endpoint is not affected by error handling."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
