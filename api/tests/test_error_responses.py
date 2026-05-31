from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app


def _ensure_test_routes() -> None:
    route_paths = {route.path for route in app.routes}

    if "/_test/auth-failed" not in route_paths:
        @app.get("/_test/auth-failed")
        async def auth_failed():
            raise HTTPException(status_code=401, detail="Invalid token")

    if "/_test/rate-limited" not in route_paths:
        @app.get("/_test/rate-limited")
        async def rate_limited():
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if "/_test/internal-error" not in route_paths:
        @app.get("/_test/internal-error")
        async def internal_error():
            raise RuntimeError("boom")


_ensure_test_routes()
client = TestClient(app, raise_server_exceptions=False)


def assert_error_schema(payload: dict, expected_code: str) -> None:
    assert payload["code"] == expected_code
    assert isinstance(payload["message"], str)
    assert isinstance(payload["details"], dict)
    assert isinstance(payload["request_id"], str)
    assert payload["request_id"]


def test_validation_error_has_field_level_details():
    response = client.get("/agents", params={"limit": 101})

    assert response.status_code == 422
    data = response.json()
    assert_error_schema(data, "VALIDATION_ERROR")
    assert isinstance(data["details"].get("fields"), list)
    assert any(field["field"].endswith("limit") for field in data["details"]["fields"])
    assert response.headers["X-Request-ID"] == data["request_id"]


def test_not_found_error_schema():
    response = client.get("/agents/missing-agent")

    assert response.status_code == 404
    data = response.json()
    assert_error_schema(data, "NOT_FOUND")
    assert response.headers["X-Request-ID"] == data["request_id"]


def test_auth_failed_error_schema():
    response = client.get("/_test/auth-failed")

    assert response.status_code == 401
    data = response.json()
    assert_error_schema(data, "AUTH_FAILED")
    assert response.headers["X-Request-ID"] == data["request_id"]


def test_rate_limited_error_schema():
    response = client.get("/_test/rate-limited")

    assert response.status_code == 429
    data = response.json()
    assert_error_schema(data, "RATE_LIMITED")
    assert response.headers["X-Request-ID"] == data["request_id"]


def test_internal_error_schema():
    response = client.get("/_test/internal-error")

    assert response.status_code == 500
    data = response.json()
    assert_error_schema(data, "INTERNAL_ERROR")
    assert response.headers["X-Request-ID"] == data["request_id"]
