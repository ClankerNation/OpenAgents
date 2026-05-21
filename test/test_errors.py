"""Tests for structured error responses.

Contributor: iyop666 (https://github.com/iyop666)
"""

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.errors import (
    ErrorCode,
    error_response,
    register_error_handlers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/not-found")
    async def not_found():
        raise HTTPException(status_code=404, detail="Resource not found")

    @app.get("/auth-fail")
    async def auth_fail():
        raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="Role 'admin' required")

    @app.get("/bad-request")
    async def bad_request():
        raise HTTPException(status_code=400, detail="Missing required field")

    @app.get("/conflict")
    async def conflict():
        raise HTTPException(status_code=409, detail="Resource already exists")

    @app.get("/rate-limited")
    async def rate_limited():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    @app.get("/internal-error")
    async def internal_error():
        raise HTTPException(status_code=500, detail="Internal server error")

    class Item(BaseModel):
        name: str
        quantity: int

    @app.post("/validate")
    async def validate(item: Item):
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# Schema compliance tests
# ---------------------------------------------------------------------------

class TestErrorSchema:
    def test_error_has_code_message_request_id(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/not-found")
        body = resp.json()
        assert "error" in body
        err = body["error"]
        assert "code" in err
        assert "message" in err
        assert "request_id" in err

    def test_success_unchanged(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Error code tests
# ---------------------------------------------------------------------------

class TestErrorCodes:
    def test_not_found_code(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/not-found")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == ErrorCode.NOT_FOUND

    def test_auth_failed_code(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/auth-fail")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == ErrorCode.AUTH_FAILED

    def test_forbidden_code(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/forbidden")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == ErrorCode.FORBIDDEN

    def test_bad_request_code(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/bad-request")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == ErrorCode.BAD_REQUEST

    def test_conflict_code(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/conflict")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == ErrorCode.CONFLICT

    def test_rate_limited_code(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/rate-limited")
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == ErrorCode.RATE_LIMITED

    def test_internal_error_code(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/internal-error")
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == ErrorCode.INTERNAL_ERROR


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------

class TestValidationErrors:
    def test_validation_error_has_field_details(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.post("/validate", json={"name": "test"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == ErrorCode.VALIDATION_ERROR
        assert "details" in body["error"]
        details = body["error"]["details"]
        assert len(details) > 0
        assert any("quantity" in d["field"] for d in details)

    def test_validation_error_type_field(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.post("/validate", json={"name": 123, "quantity": "not-a-number"})
        assert resp.status_code == 422
        details = resp.json()["error"]["details"]
        assert len(details) > 0


# ---------------------------------------------------------------------------
# Request ID tests
# ---------------------------------------------------------------------------

class TestRequestId:
    def test_request_id_from_header(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/not-found", headers={"X-Request-ID": "my-req-123"})
        assert resp.json()["error"]["request_id"] == "my-req-123"

    def test_request_id_auto_generated(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/not-found")
        req_id = resp.json()["error"]["request_id"]
        assert len(req_id) > 0  # UUID format


# ---------------------------------------------------------------------------
# Error response builder test
# ---------------------------------------------------------------------------

class TestErrorResponseBuilder:
    def test_error_response_with_details(self):
        resp = error_response(
            status_code=400,
            code="TEST_ERROR",
            message="Test message",
            details={"field": "value"},
            request_id="test-123",
        )
        import json
        body = json.loads(resp.body)
        assert body["error"]["code"] == "TEST_ERROR"
        assert body["error"]["details"]["field"] == "value"

    def test_error_response_without_details(self):
        resp = error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Oops",
            request_id="test-456",
        )
        import json
        body = json.loads(resp.body)
        assert "details" not in body["error"]
