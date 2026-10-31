"""Tests for structured error responses."""

import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_404_returns_structured_error(client):
    """404 returns structured error with code, message, details, request_id."""
    response = client.get("/agents/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "NOT_FOUND"
    assert "message" in data
    assert "details" in data
    assert "request_id" in data


def test_422_returns_structured_error(client):
    """422 validation error returns structured error with field details."""
    response = client.get("/tasks/abc")
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "message" in data
    assert "details" in data
    assert "request_id" in data


def test_error_includes_request_id(client):
    """Error response includes request_id."""
    response = client.get("/agents/nonexistent", headers={"X-Request-ID": "test-123"})
    data = response.json()
    assert data["request_id"] == "test-123"


def test_error_response_schema(client):
    """All error responses follow the schema."""
    response = client.get("/agents/nonexistent")
    data = response.json()
    assert set(data.keys()) == {"code", "message", "details", "request_id"}


def test_404_error_code(client):
    """404 maps to NOT_FOUND code."""
    response = client.get("/agents/nonexistent")
    assert response.json()["code"] == "NOT_FOUND"
