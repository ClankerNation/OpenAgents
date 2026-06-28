"""Tests for structured error responses."""

import uuid
import os
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from typing import Optional

os.environ["JWT_SECRET"] = "test-secret-key"

from api.errors import (
    register_error_handlers,
    AppError,
    ErrorCode,
    error_response,
)


def create_test_app():
    app = FastAPI()
    register_error_handlers(app)

    class Item(BaseModel):
        name: str = Field(..., min_length=1)
        value: int

    @app.get("/not-found")
    async def not_found():
        raise AppError(ErrorCode.NOT_FOUND, details={"id": 123}, status_code=404)

    @app.get("/auth-failed")
    async def auth_failed():
        raise AppError(ErrorCode.AUTH_FAILED, status_code=401)

    @app.get("/forbidden")
    async def forbidden():
        raise AppError(ErrorCode.FORBIDDEN, status_code=403)

    @app.get("/rate-limited")
    async def rate_limited():
        raise AppError(ErrorCode.RATE_LIMITED, status_code=429)

    @app.get("/internal-error")
    async def internal_error():
        raise AppError(ErrorCode.INTERNAL_ERROR, status_code=500)

    @app.get("/unexpected-error")
    async def unexpected_error():
        raise ValueError("Something went wrong")

    @app.post("/validate")
    async def validate(item: Item):
        return item

    @app.get("/custom-error")
    async def custom_error():
        raise AppError(
            ErrorCode.CONFLICT,
            message="Agent name already exists",
            details={"field": "name", "value": "my-agent"},
            status_code=409,
        )

    return app


class TestErrorSchema:
    def setup_method(self):
        self.app = create_test_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_not_found_error(self):
        resp = self.client.get("/not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        error = body["error"]
        assert error["code"] == "NOT_FOUND"
        assert error["message"] == "Resource not found"
        assert error["details"] == {"id": 123}
        assert "request_id" in error

    def test_auth_failed_error(self):
        resp = self.client.get("/auth-failed")
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["code"] == "AUTH_FAILED"

    def test_forbidden_error(self):
        resp = self.client.get("/forbidden")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["code"] == "FORBIDDEN"

    def test_rate_limited_error(self):
        resp = self.client.get("/rate-limited")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "RATE_LIMITED"

    def test_internal_error(self):
        resp = self.client.get("/internal-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"

    def test_unexpected_exception_returns_500(self):
        resp = self.client.get("/unexpected-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"

    def test_validation_error(self):
        resp = self.client.post("/validate", json={"name": "", "value": "not-a-number"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "fields" in body["error"]["details"]

    def test_custom_error_message(self):
        resp = self.client.get("/custom-error")
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "CONFLICT"
        assert body["error"]["message"] == "Agent name already exists"
        assert body["error"]["details"]["field"] == "name"

    def test_request_id_present(self):
        resp = self.client.get("/not-found")
        body = resp.json()
        request_id = body["error"]["request_id"]
        assert request_id
        uuid.UUID(request_id)

    def test_all_error_codes_have_messages(self):
        for code in [
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.NOT_FOUND,
            ErrorCode.AUTH_FAILED,
            ErrorCode.FORBIDDEN,
            ErrorCode.RATE_LIMITED,
            ErrorCode.CONFLICT,
            ErrorCode.INTERNAL_ERROR,
        ]:
            resp = error_response(code=code, status_code=400)
            assert resp.status_code == 400


class TestHealthEndpoint:
    def setup_method(self):
        self.app = create_test_app()
        self.client = TestClient(self.app)

        @self.app.get("/health")
        async def health():
            return {"status": "ok"}

    def test_health_not_affected_by_error_handler(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
