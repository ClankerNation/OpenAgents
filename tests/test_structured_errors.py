from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import ERROR_CODES, app


@app.get("/__test__/auth-failed")
async def auth_failed():
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/__test__/rate-limited")
async def rate_limited():
    raise HTTPException(
        status_code=429,
        detail="Rate limit exceeded",
        headers={"Retry-After": "60"},
    )


@app.get("/__test__/internal-error")
async def internal_error():
    raise RuntimeError("boom")


def assert_error_schema(payload, expected_code, request_id="test-request-id"):
    assert payload["code"] == expected_code
    assert isinstance(payload["message"], str)
    assert isinstance(payload["details"], dict)
    assert payload["request_id"] == request_id


def test_error_codes_are_documented():
    assert ERROR_CODES == {
        "VALIDATION_ERROR": "The request payload, path, or query parameters failed validation.",
        "NOT_FOUND": "The requested resource does not exist.",
        "AUTH_FAILED": "Authentication or authorization failed.",
        "RATE_LIMITED": "The request was rate limited.",
        "INTERNAL_ERROR": "An unexpected server error occurred.",
    }


def test_not_found_error_has_consistent_schema_and_request_id():
    client = TestClient(app)

    response = client.get("/agents/missing", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert_error_schema(response.json(), "NOT_FOUND")
    assert response.json()["message"] == "Agent not found"


def test_validation_error_includes_field_level_details():
    client = TestClient(app)

    response = client.get("/tasks/not-an-int", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 422
    payload = response.json()
    assert_error_schema(payload, "VALIDATION_ERROR")
    assert payload["message"] == "Request validation failed"
    assert payload["details"]["fields"]
    assert any(field_error["field"] == "path.task_id" for field_error in payload["details"]["fields"])


def test_auth_failed_error_uses_standard_code():
    client = TestClient(app)

    response = client.get("/__test__/auth-failed", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 401
    assert_error_schema(response.json(), "AUTH_FAILED")
    assert response.json()["message"] == "Invalid credentials"


def test_rate_limited_error_uses_standard_code_and_preserves_retry_header():
    client = TestClient(app)

    response = client.get("/__test__/rate-limited", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert_error_schema(response.json(), "RATE_LIMITED")


def test_internal_error_uses_standard_code_without_leaking_exception():
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/__test__/internal-error", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 500
    payload = response.json()
    assert_error_schema(payload, "INTERNAL_ERROR")
    assert payload["message"] == "An unexpected server error occurred."
    assert "boom" not in str(payload)
