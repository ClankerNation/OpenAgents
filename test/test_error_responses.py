"""Tests for structured error responses."""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_not_found_error_structure():
    """Test that 404 errors return structured response."""
    response = client.get("/agents/nonexistent")
    assert response.status_code == 404

    data = response.json()
    assert "code" in data
    assert "message" in data
    assert "request_id" in data
    assert data["code"] == "NOT_FOUND"
    assert "agent_id" in data.get("details", {})


def test_not_found_task_error():
    """Test that task not found returns structured response."""
    response = client.get("/tasks/99999")
    assert response.status_code == 404

    data = response.json()
    assert data["code"] == "NOT_FOUND"
    assert "task_id" in data.get("details", {})
    assert data["request_id"] is not None


def test_validation_error_structure():
    """Test that validation errors return structured response with field details."""
    response = client.get("/agents?limit=invalid")
    assert response.status_code == 422

    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "message" in data
    assert "details" in data
    assert "validation_errors" in data["details"]
    assert len(data["details"]["validation_errors"]) > 0

    # Check field-level details
    error = data["details"]["validation_errors"][0]
    assert "field" in error
    assert "message" in error
    assert "type" in error


def test_validation_error_negative_limit():
    """Test validation error for negative limit."""
    response = client.get("/agents?limit=-1")
    assert response.status_code == 422

    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "validation_errors" in data["details"]


def test_validation_error_limit_too_large():
    """Test validation error for limit exceeding maximum."""
    response = client.get("/agents?limit=200")
    assert response.status_code == 422

    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"


def test_request_id_in_response():
    """Test that all error responses include request_id."""
    response = client.get("/agents/nonexistent")
    data = response.json()

    assert "request_id" in data
    assert data["request_id"] is not None
    assert len(data["request_id"]) > 0


def test_request_id_in_header():
    """Test that request_id is also in response headers."""
    response = client.get("/agents/nonexistent")
    assert "X-Request-ID" in response.headers

    data = response.json()
    assert data["request_id"] == response.headers["X-Request-ID"]


def test_custom_request_id_preserved():
    """Test that custom X-Request-ID header is preserved."""
    custom_id = "test-request-123"
    response = client.get("/agents/nonexistent", headers={"X-Request-ID": custom_id})

    assert response.headers["X-Request-ID"] == custom_id
    data = response.json()
    assert data["request_id"] == custom_id


def test_successful_request_has_request_id():
    """Test that successful requests also get request_id in headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers


def test_error_code_consistency():
    """Test that error codes are consistent across similar errors."""
    response1 = client.get("/agents/nonexistent1")
    response2 = client.get("/agents/nonexistent2")

    assert response1.json()["code"] == response2.json()["code"]
    assert response1.json()["code"] == "NOT_FOUND"


def test_validation_error_multiple_fields():
    """Test validation errors with multiple invalid fields."""
    response = client.get("/agents?limit=invalid&offset=invalid")
    assert response.status_code == 422

    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    errors = data["details"]["validation_errors"]
    assert len(errors) >= 2


def test_error_message_clarity():
    """Test that error messages are clear and helpful."""
    response = client.get("/agents/nonexistent")
    data = response.json()

    assert data["message"]
    assert len(data["message"]) > 0
    assert isinstance(data["message"], str)
