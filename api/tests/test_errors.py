from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.errors import code_for_status
from api.main import app


def _install_error_routes() -> None:
    known_paths = {route.path for route in app.routes}
    if "/_test/error400" not in known_paths:
        @app.get("/_test/error400")
        async def _error400():
            raise HTTPException(status_code=400, detail="Bad request test")

    if "/_test/error401" not in known_paths:
        @app.get("/_test/error401")
        async def _error401():
            raise HTTPException(status_code=401, detail="Auth failed test")

    if "/_test/error429" not in known_paths:
        @app.get("/_test/error429")
        async def _error429():
            raise HTTPException(status_code=429, detail="Rate limit test")

    if "/_test/error500" not in known_paths:
        @app.get("/_test/error500")
        async def _error500():
            raise RuntimeError("boom")


_install_error_routes()
client = TestClient(app, raise_server_exceptions=False)


def test_not_found_error_schema_and_request_id():
    response = client.get("/agents/missing-agent")
    body = response.json()

    assert response.status_code == 404
    assert body["code"] == "NOT_FOUND"
    assert body["message"] == "Agent not found"
    assert isinstance(body["details"], dict)
    assert body["request_id"]


def test_request_id_pass_through():
    response = client.get("/agents/missing-agent", headers={"X-Request-ID": "req-123"})
    body = response.json()

    assert body["request_id"] == "req-123"
    assert response.headers["X-Request-ID"] == "req-123"


def test_validation_error_has_field_details():
    response = client.get("/tasks/not-an-int")
    body = response.json()

    assert response.status_code == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Request validation failed"
    assert "fields" in body["details"]
    assert "task_id" in body["details"]["fields"]
    assert body["request_id"]


def test_status_code_mapping_covers_required_codes():
    assert code_for_status(400) == "BAD_REQUEST"
    assert code_for_status(401) == "AUTH_FAILED"
    assert code_for_status(403) == "AUTH_FAILED"
    assert code_for_status(404) == "NOT_FOUND"
    assert code_for_status(429) == "RATE_LIMITED"
    assert code_for_status(500) == "INTERNAL_ERROR"


def test_bad_request_and_auth_and_rate_limited_errors_use_structured_schema():
    for path, expected_code, status in (
        ("/_test/error400", "BAD_REQUEST", 400),
        ("/_test/error401", "AUTH_FAILED", 401),
        ("/_test/error429", "RATE_LIMITED", 429),
    ):
        response = client.get(path)
        body = response.json()
        assert response.status_code == status
        assert body["code"] == expected_code
        assert body["request_id"]
        assert "message" in body
        assert isinstance(body["details"], dict)


def test_internal_error_uses_structured_schema():
    response = client.get("/_test/error500")
    body = response.json()

    assert response.status_code == 500
    assert body["code"] == "INTERNAL_ERROR"
    assert body["message"] == "Internal server error"
    assert body["request_id"]
