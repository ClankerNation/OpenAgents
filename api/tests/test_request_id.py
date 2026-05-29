import logging
import re

from fastapi.testclient import TestClient

from api.main import REQUEST_ID_HEADER, app


client = TestClient(app)


def test_response_has_generated_request_id_header():
    response = client.get("/health")

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        request_id,
    )


def test_client_request_id_is_preserved():
    response = client.get("/health", headers={REQUEST_ID_HEADER: "trace-123"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "trace-123"


def test_generated_ids_are_unique_per_request():
    first = client.get("/health").headers[REQUEST_ID_HEADER]
    second = client.get("/health").headers[REQUEST_ID_HEADER]

    assert first != second


def test_request_id_is_present_on_error_response():
    response = client.get("/agents/missing-agent", headers={REQUEST_ID_HEADER: "error-trace"})

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "error-trace"


def test_logs_include_request_id(caplog):
    with caplog.at_level(logging.INFO, logger="openagents.api"):
        response = client.get("/health", headers={REQUEST_ID_HEADER: "log-trace"})

    assert response.status_code == 200
    records = [record for record in caplog.records if record.name == "openagents.api"]
    assert records
    assert all(record.request_id == "log-trace" for record in records)
