"""Tests for structured error responses (bounty issue #202)."""

from fastapi.testclient import TestClient

from ..main import app, ERROR_CODE_NOT_FOUND, APIError


client = TestClient(app)


def test_not_found_error_schema():
    """404 returns structured error with code, message, details, request_id."""
    response = client.get("/agents/nonexistent")
    assert response.status_code == 404

    data = response.json()
    assert data["code"] == ERROR_CODE_NOT_FOUND
    assert "message" in data
    assert "details" in data
    assert "request_id" in data
    assert data["details"]["agent_id"] == "nonexistent"


def test_request_id_header():
    """Every response includes X-Request-ID header."""
    response = client.get("/agents")
    assert "x-request-id" in response.headers


def test_health_still_works():
    """Health endpoint still returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
