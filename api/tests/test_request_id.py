import io
import logging
import uuid

from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_response_has_request_id_header():
    response = client.get("/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    uuid.UUID(request_id)


def test_client_provided_request_id_is_preserved():
    expected = "trace-parent-id-123"
    response = client.get("/health", headers={"X-Request-ID": expected})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == expected


def test_generated_request_ids_are_unique():
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]
    assert first != second


def test_logs_include_request_id():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("openagents.api")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        response = client.get("/health", headers={"X-Request-ID": "log-correlation-id"})
        assert response.status_code == 200
    finally:
        logger.removeHandler(handler)

    logs = stream.getvalue()
    assert "log-correlation-id" in logs
