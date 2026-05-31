"""Tests for structured API error responses."""

from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_not_found_errors_are_structured():
    response = client.get("/agents/missing-agent")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Agent not found"
    assert body["error"]["details"] == {"agent_id": "missing-agent"}
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "detail" not in body


def test_validation_errors_include_field_details():
    response = client.get("/agents?limit=-1&offset=-1")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    fields = {error["field"] for error in body["error"]["details"]["validation_errors"]}
    assert "query.limit" in fields
    assert "query.offset" in fields
    assert "detail" not in body


def test_custom_request_id_is_preserved_on_errors():
    response = client.get("/tasks/999", headers={"X-Request-ID": "req-test-123"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "req-test-123"
    assert response.json()["error"]["request_id"] == "req-test-123"

