"""
Public regression tests for structured API errors.

@fix-author: Codex
@date: 2026-08-06
@platform-instructions: Private session and startup instructions intentionally omitted.
@runtime: os=Darwin, arch=arm64, home_dir=[redacted], working_dir=[redacted], shell=zsh
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.main import app as production_app
from api.middleware.exception_handler import register_error_handlers


def make_error_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/validation")
    async def validation(value: int):
        return {"value": value}

    @app.get("/auth")
    async def auth_error():
        raise HTTPException(status_code=401, detail="Token is invalid")

    @app.get("/rate")
    async def rate_error():
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": "3"},
        )

    @app.get("/internal")
    async def internal_error():
        raise RuntimeError("private implementation detail")

    return app


client = TestClient(make_error_app(), raise_server_exceptions=False)


def test_validation_errors_include_field_details_and_request_id():
    response = client.get(
        "/validation?value=not-an-integer",
        headers={"X-Request-ID": "req-validation-202"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert "query.value" in payload["details"]["fields"]
    assert payload["request_id"] == "req-validation-202"
    assert response.headers["X-Request-ID"] == "req-validation-202"


def test_http_errors_use_required_codes_and_preserve_headers():
    not_found = client.get("/missing")
    assert not_found.status_code == 404
    assert not_found.json()["code"] == "NOT_FOUND"
    assert isinstance(not_found.json()["details"], dict)

    auth = client.get("/auth")
    assert auth.status_code == 401
    assert auth.json()["code"] == "AUTH_FAILED"

    rate = client.get("/rate")
    assert rate.status_code == 429
    assert rate.json()["code"] == "RATE_LIMITED"
    assert rate.headers["Retry-After"] == "3"


def test_internal_errors_are_safe_and_structured():
    response = client.get("/internal")

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "INTERNAL_ERROR"
    assert payload["message"] == "An unexpected error occurred"
    assert payload["details"] == {}
    assert "private implementation detail" not in response.text
    assert payload["request_id"]


def test_production_app_registers_handlers():
    response = TestClient(production_app).get("/agents/not-found")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
