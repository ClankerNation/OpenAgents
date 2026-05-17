import logging
from uuid import UUID

from fastapi.testclient import TestClient

from api.main import REQUEST_ID_HEADER, app, logger


def test_response_includes_generated_request_id():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    assert UUID(request_id)


def test_client_provided_request_id_is_preserved():
    client = TestClient(app)
    request_id = "trace-openagents-178"

    response = client.get("/health", headers={REQUEST_ID_HEADER: request_id})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == request_id


def test_generated_request_ids_are_unique_per_request():
    client = TestClient(app)

    first = client.get("/health").headers[REQUEST_ID_HEADER]
    second = client.get("/health").headers[REQUEST_ID_HEADER]

    assert first != second


def test_logs_include_request_id(caplog):
    client = TestClient(app)
    request_id = "trace-log-correlation"

    with caplog.at_level(logging.INFO, logger=logger.name):
        response = client.get("/health", headers={REQUEST_ID_HEADER: request_id})

    assert response.status_code == 200
    completed_logs = [
        record
        for record in caplog.records
        if record.name == logger.name and record.message == "request completed"
    ]
    assert completed_logs
    assert all(record.request_id == request_id for record in completed_logs)
    assert any(
        f":{request_id}:request completed" in handler.format(completed_logs[-1])
        for handler in logger.handlers
    )


def test_unhandled_exception_response_includes_request_id():
    @app.get("/__request_id_failure")
    async def request_id_failure():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    request_id = "trace-error-correlation"

    response = client.get("/__request_id_failure", headers={REQUEST_ID_HEADER: request_id})

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == request_id
