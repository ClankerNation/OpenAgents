from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.middleware.ratelimit import RateLimitConfig, RateLimitMiddleware, _request_counts


def _assert_error_shape(payload: dict) -> None:
    assert "code" in payload
    assert "message" in payload
    assert "details" in payload
    assert "request_id" in payload
    assert isinstance(payload["details"], dict)
    assert isinstance(payload["request_id"], str)
    assert payload["request_id"]


def test_not_found_is_structured_with_code_and_request_id():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/agents/nonexistent")

    assert response.status_code == 404
    payload = response.json()
    _assert_error_shape(payload)
    assert payload["code"] == "NOT_FOUND"


def test_validation_error_includes_field_level_details():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/agents", params={"limit": 101})

    assert response.status_code == 422
    payload = response.json()
    _assert_error_shape(payload)
    assert payload["code"] == "VALIDATION_ERROR"
    assert "fields" in payload["details"]
    assert any(field["field"] == "query.limit" for field in payload["details"]["fields"])


def test_auth_failed_is_mapped_from_401():
    path = f"/_test_auth_failed_{uuid4().hex}"

    @app.get(path)
    async def _auth_failed_route():
        raise HTTPException(status_code=401, detail="Invalid token")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(path)

    assert response.status_code == 401
    payload = response.json()
    _assert_error_shape(payload)
    assert payload["code"] == "AUTH_FAILED"


def test_internal_error_is_structured():
    path = f"/_test_internal_error_{uuid4().hex}"

    @app.get(path)
    async def _internal_error_route():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(path)

    assert response.status_code == 500
    payload = response.json()
    _assert_error_shape(payload)
    assert payload["code"] == "INTERNAL_ERROR"


def test_rate_limited_is_structured():
    _request_counts.clear()
    rate_app = FastAPI()

    @rate_app.middleware("http")
    async def attach_request_id(request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    rate_app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(requests_per_window=1, window_seconds=60),
    )

    @rate_app.get("/limited")
    async def limited():
        return {"ok": True}

    client = TestClient(rate_app, raise_server_exceptions=False)
    assert client.get("/limited").status_code == 200

    response = client.get("/limited")
    assert response.status_code == 429
    payload = response.json()
    _assert_error_shape(payload)
    assert payload["code"] == "RATE_LIMITED"
    assert "retry_after" in payload["details"]
