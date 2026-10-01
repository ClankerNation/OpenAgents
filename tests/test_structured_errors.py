"""Tests for the structured API error schema (issue #202).

Covers: schema shape, each required error code, field-level validation
details, and request_id propagation.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.errors import (
    AuthFailedError,
    ErrorCode,
    NotFoundError,
    RateLimitedError,
    ValidationAPIError,
    register_exception_handlers,
)

client = TestClient(app, raise_server_exceptions=False)

REQUIRED_KEYS = {"code", "message", "details", "request_id"}


def assert_error_shape(body: dict, code: str):
    assert REQUIRED_KEYS.issubset(body.keys())
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["details"], dict)
    assert body["request_id"]


def test_not_found_error_schema():
    resp = client.get("/agents/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert_error_shape(body, ErrorCode.NOT_FOUND.value)
    assert body["details"]["agent_id"] == "does-not-exist"


def test_task_not_found_error_schema():
    resp = client.get("/tasks/999999")
    assert resp.status_code == 404
    body = resp.json()
    assert_error_shape(body, ErrorCode.NOT_FOUND.value)
    assert body["details"]["task_id"] == 999999


def test_validation_error_includes_field_details():
    # limit has le=100, so this trips FastAPI/pydantic request validation
    resp = client.get("/agents", params={"limit": 9999})
    assert resp.status_code == 400
    body = resp.json()
    assert_error_shape(body, ErrorCode.VALIDATION_ERROR.value)
    fields = body["details"]["fields"]
    assert len(fields) >= 1
    assert any("limit" in f["field"] for f in fields)


def test_request_id_present_and_matches_header():
    resp = client.get("/agents/does-not-exist")
    body = resp.json()
    assert resp.headers.get("X-Request-ID")
    assert resp.headers["X-Request-ID"] == body["request_id"]


def test_request_id_unique_per_request():
    first = client.get("/agents/does-not-exist").json()["request_id"]
    second = client.get("/agents/does-not-exist").json()["request_id"]
    assert first != second


def test_health_endpoint_unaffected():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --- Error codes not reachable through main.py's current routes are
# exercised against a minimal app wired with the same handlers. ---


def _build_probe_app() -> FastAPI:
    probe = FastAPI()
    register_exception_handlers(probe)

    @probe.middleware("http")
    async def add_request_id(request, call_next):
        import uuid

        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @probe.get("/auth-failed")
    async def _auth_failed():
        raise AuthFailedError("Invalid credentials")

    @probe.get("/rate-limited")
    async def _rate_limited():
        raise RateLimitedError("Too many requests", details={"retry_after": 30})

    @probe.get("/validation")
    async def _validation():
        raise ValidationAPIError("Bad input", details={"fields": [{"field": "name", "message": "required"}]})

    @probe.get("/not-found")
    async def _not_found():
        raise NotFoundError("Missing")

    @probe.get("/boom")
    async def _boom():
        raise RuntimeError("unexpected failure")

    @probe.get("/legacy-http-exception")
    async def _legacy():
        raise HTTPException(status_code=401, detail="legacy unauthorized")

    return probe


probe_client = TestClient(_build_probe_app(), raise_server_exceptions=False)


def test_auth_failed_error_code():
    resp = probe_client.get("/auth-failed")
    assert resp.status_code == 401
    assert_error_shape(resp.json(), ErrorCode.AUTH_FAILED.value)


def test_rate_limited_error_code():
    resp = probe_client.get("/rate-limited")
    assert resp.status_code == 429
    body = resp.json()
    assert_error_shape(body, ErrorCode.RATE_LIMITED.value)
    assert body["details"]["retry_after"] == 30


def test_validation_error_code_with_details():
    resp = probe_client.get("/validation")
    assert resp.status_code == 400
    body = resp.json()
    assert_error_shape(body, ErrorCode.VALIDATION_ERROR.value)
    assert body["details"]["fields"][0]["field"] == "name"


def test_not_found_error_code():
    resp = probe_client.get("/not-found")
    assert resp.status_code == 404
    assert_error_shape(resp.json(), ErrorCode.NOT_FOUND.value)


def test_internal_error_code_on_unhandled_exception():
    resp = probe_client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert_error_shape(body, ErrorCode.INTERNAL_ERROR.value)
    # Internal errors must never leak exception internals to the client
    assert "unexpected failure" not in body["message"]


def test_legacy_http_exception_is_normalized():
    resp = probe_client.get("/legacy-http-exception")
    assert resp.status_code == 401
    body = resp.json()
    assert_error_shape(body, ErrorCode.AUTH_FAILED.value)
    assert body["message"] == "legacy unauthorized"
