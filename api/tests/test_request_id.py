"""
Tests for request ID middleware in api/main.py
Issue: #164 — Add request ID middleware for log correlation
"""
import pytest
from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


def test_request_id_header_present():
    """Each response should have X-Request-ID header."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    # Should be a valid UUID
    import uuid
    uuid.UUID(response.headers["x-request-id"])


def test_request_id_unique_per_request():
    """Each request should get a unique request ID."""
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


def test_client_request_id_preserved():
    """Client-provided X-Request-ID should be preserved for distributed tracing."""
    custom_id = "test-trace-id-12345"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id


def test_request_id_on_error_responses():
    """Request ID should be present even on error responses."""
    response = client.get("/agents/nonexistent")
    assert response.status_code == 404
    assert "x-request-id" in response.headers


def test_request_id_on_all_routes():
    """Request ID should be present on all routes."""
    routes = ["/health", "/agents", "/tasks", "/leaderboard"]
    for route in routes:
        response = client.get(route)
        assert "x-request-id" in response.headers, f"Missing X-Request-ID on {route}"
