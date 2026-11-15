from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_response_contains_request_id():
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers


def test_client_request_id_is_echoed():
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_requests_without_header_get_distinct_ids():
    first = client.get("/health")
    second = client.get("/health")
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
