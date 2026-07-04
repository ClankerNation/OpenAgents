import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.middleware.errors import ErrorResponse

client = TestClient(app)


def test_404_returns_structured_error():
    response = client.get("/nonexistent")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert "message" in body
    assert "request_id" in body
    assert "details" in body


def test_request_id_header_present():
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) > 0


def test_request_id_preserved_in_error_response():
    response = client.get("/nonexistent", headers={"X-Request-ID": "custom-id-123"})
    assert response.status_code == 404
    body = response.json()
    assert body["request_id"] == "custom-id-123"


def test_health_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_error_response_schema():
    response = client.get("/nonexistent")
    assert response.status_code == 404
    body = response.json()
    assert "code" in body
    assert "message" in body
    assert "request_id" in body
    assert body["code"] == "NOT_FOUND"
