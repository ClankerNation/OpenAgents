"""
Tests for structured error responses (Issue #202).

Run: cd api && python -m pytest tests/test_errors.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ─── Error Response Schema ───────────────────────────────────────

def assert_error_shape(response, expected_code: str, expected_status: int):
    """Verify the standardized error response shape."""
    assert response.status_code == expected_status
    body = response.json()
    assert "code" in body, f"Missing 'code' in {body}"
    assert body["code"] == expected_code
    assert "message" in body, f"Missing 'message' in {body}"
    assert isinstance(body["message"], str)
    assert "request_id" in body, f"Missing 'request_id' in {body}"
    assert len(body["request_id"]) > 0
    assert "timestamp" in body, f"Missing 'timestamp' in {body}"
    # request_id should be a valid UUID
    import uuid
    try:
        uuid.UUID(body["request_id"])
    except ValueError:
        pytest.fail(f"request_id is not a valid UUID: {body['request_id']}")
    return body


def test_request_id_header():
    """Every response should include X-Request-ID header."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


# ─── 404 NOT_FOUND ───────────────────────────────────────────────

def test_not_found_agent():
    """GET /agents/nonexistent → 404 NOT_FOUND with structured error."""
    response = client.get("/agents/nonexistent-agent")
    body = assert_error_shape(response, "NOT_FOUND", 404)
    assert "Agent not found" in body["message"]


def test_not_found_task():
    """GET /tasks/99999 → 404 NOT_FOUND with structured error."""
    response = client.get("/tasks/99999")
    body = assert_error_shape(response, "NOT_FOUND", 404)
    assert "Task not found" in body["message"]


# ─── 422 VALIDATION_ERROR ────────────────────────────────────────

def test_validation_error_list_agents():
    """GET /agents?limit=999 → 422 VALIDATION_ERROR with field details."""
    response = client.get("/agents?limit=999")
    body = assert_error_shape(response, "VALIDATION_ERROR", 422)
    assert "details" in body, f"Missing 'details' in {body}"
    assert isinstance(body["details"], list)
    assert len(body["details"]) > 0, "Expected at least one validation detail"
    detail = body["details"][0]
    assert "field" in detail
    assert "message" in detail
    assert "type" in detail
    # The field should reference 'limit'
    assert "limit" in detail["field"].lower()


def test_validation_error_multiple_fields():
    """Multiple validation errors should all be listed."""
    response = client.get("/agents?limit=999&min_reputation=abc")
    body = assert_error_shape(response, "VALIDATION_ERROR", 422)
    assert len(body["details"]) == 2, f"Expected 2 details, got {len(body['details'])}"


def test_validation_error_tasks_limit():
    """GET /tasks?limit=999 → 422 VALIDATION_ERROR."""
    response = client.get("/tasks?limit=999")
    body = assert_error_shape(response, "VALIDATION_ERROR", 422)
    assert len(body["details"]) > 0


# ─── 422 VALIDATION_ERROR (tasks offset negative) ─────────────────

def test_validation_error_negative_offset():
    """GET /tasks?offset=-5 → 422 with field details."""
    response = client.get("/tasks?offset=-5")
    body = assert_error_shape(response, "VALIDATION_ERROR", 422)
    assert any("offset" in d["field"].lower() for d in body["details"])


# ─── Request ID Consistency ──────────────────────────────────────

def test_request_id_consistent():
    """Multiple error attributes should coexist correctly."""
    response = client.get("/agents/nonexistent-agent")
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["request_id"] is not None
    assert body["timestamp"] is not None


def test_each_request_unique_id():
    """Each request should get a unique request_id."""
    ids = set()
    for _ in range(5):
        response = client.get("/agents/nonexistent-agent")
        ids.add(response.json()["request_id"])
    assert len(ids) == 5, f"Expected 5 unique IDs, got {len(ids)}"


# ─── Edge Cases ──────────────────────────────────────────────────

def test_invalid_limit_string():
    """Non-integer limit should return validation error."""
    response = client.get("/agents?limit=notanumber")
    body = assert_error_shape(response, "VALIDATION_ERROR", 422)
    assert any("limit" in d["field"].lower() for d in body["details"])


def test_missing_required_path_param():
    """FastAPI should handle this as a routing error."""
    # Test with a path that doesn't match any route
    response = client.get("/agents/")
    # Should work (matches list endpoint redirect) or return a structured error
    # FastAPI redirects trailing slash by default — just verify it doesn't 500
    assert response.status_code in (200, 307, 404, 422)
