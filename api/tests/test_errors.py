from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient

from api.errors import install_error_handlers
from api.middleware.ratelimit import RateLimitMiddleware, RateLimitConfig


def build_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/validation")
    async def validation(limit: int = Query(..., ge=1)):
        return {"limit": limit}

    @app.get("/not-found")
    async def not_found():
        raise HTTPException(status_code=404, detail="Thing not found")

    @app.get("/auth")
    async def auth_failed():
        raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/internal")
    async def internal_error():
        raise RuntimeError("boom")

    return app


def assert_error(response, code: str):
    payload = response.json()
    assert payload["error"]["code"] == code
    assert "message" in payload["error"]
    assert "details" in payload["error"]
    assert payload["error"]["request_id"]
    assert response.headers["X-Request-ID"] == payload["error"]["request_id"]


def test_validation_error_has_field_details():
    client = TestClient(build_app())

    response = client.get("/validation?limit=0")

    assert response.status_code == 422
    assert_error(response, "VALIDATION_ERROR")
    assert response.json()["error"]["details"][0]["field"] == "query.limit"


def test_not_found_error_code():
    client = TestClient(build_app())

    response = client.get("/not-found")

    assert response.status_code == 404
    assert_error(response, "NOT_FOUND")


def test_auth_failed_error_code():
    client = TestClient(build_app())

    response = client.get("/auth")

    assert response.status_code == 401
    assert_error(response, "AUTH_FAILED")


def test_internal_error_code():
    client = TestClient(build_app(), raise_server_exceptions=False)

    response = client.get("/internal")

    assert response.status_code == 500
    assert_error(response, "INTERNAL_ERROR")


def test_rate_limited_error_code():
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(RateLimitMiddleware, config=RateLimitConfig(requests_per_window=1, window_seconds=60))

    @app.get("/limited")
    async def limited():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/limited").status_code == 200

    response = client.get("/limited")

    assert response.status_code == 429
    assert_error(response, "RATE_LIMITED")
    assert response.json()["error"]["details"]["retry_after"] > 0
