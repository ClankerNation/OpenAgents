from fastapi.testclient import TestClient

from api.main import app
from api.request_id import REQUEST_ID_HEADER


def test_response_has_generated_request_id():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]


def test_client_provided_request_id_is_preserved():
    client = TestClient(app)

    response = client.get("/health", headers={REQUEST_ID_HEADER: "trace-123"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "trace-123"


def test_generated_request_ids_are_unique_per_request():
    client = TestClient(app)

    first = client.get("/health").headers[REQUEST_ID_HEADER]
    second = client.get("/health").headers[REQUEST_ID_HEADER]

    assert first != second
