"""
Tests for structured error responses with error codes (Bounty #202).

Verifies:
- ErrorCode enum values and status code mappings
- APIError exception class behaviour
- build_error_response helper output shape
- StructuredErrorMiddleware integration with FastAPI
- Route-level error responses return structured JSON with correct codes
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ..middleware.errors import (
    ErrorCode,
    APIError,
    build_error_response,
    StructuredErrorMiddleware,
    _ERROR_CODE_TO_STATUS,
)


# ── Unit Tests ──────────────────────────────────────────────────────────────

class TestErrorCode:
    """Verify ErrorCode enum has expected values and does NOT change."""

    def test_known_codes_are_distinct(self):
        codes = {c.value for c in ErrorCode}
        assert len(codes) == len(ErrorCode), "Duplicate error code values detected"

    def test_internal_error_mapping(self):
        assert _ERROR_CODE_TO_STATUS[ErrorCode.INTERNAL_ERROR] == 500

    def test_not_found_mapping(self):
        assert _ERROR_CODE_TO_STATUS[ErrorCode.NOT_FOUND] == 404

    def test_unauthorized_mapping(self):
        assert _ERROR_CODE_TO_STATUS[ErrorCode.UNAUTHORIZED] == 401

    def test_forbidden_mapping(self):
        assert _ERROR_CODE_TO_STATUS[ErrorCode.FORBIDDEN] == 403

    def test_rate_limit_mapping(self):
        assert _ERROR_CODE_TO_STATUS[ErrorCode.RATE_LIMIT_EXCEEDED] == 429

    def test_agent_not_found_mapping(self):
        assert _ERROR_CODE_TO_STATUS[ErrorCode.AGENT_NOT_FOUND] == 404

    def test_task_not_found_mapping(self):
        assert _ERROR_CODE_TO_STATUS[ErrorCode.TASK_NOT_FOUND] == 404

    def test_invalid_status_transition_mapping(self):
        assert _ERROR_CODE_TO_STATUS[ErrorCode.INVALID_STATUS_TRANSITION] == 400


class TestAPIError:
    """Verify APIError exception behaviour."""

    def test_basic_raise(self):
        with pytest.raises(APIError) as exc_info:
            raise APIError(ErrorCode.NOT_FOUND, detail="Agent not found")
        exc = exc_info.value
        assert exc.code == ErrorCode.NOT_FOUND
        assert exc.detail == "Agent not found"
        assert exc.status_code == 404

    def test_default_detail_from_code(self):
        exc = APIError(ErrorCode.INTERNAL_ERROR)
        assert exc.detail  # should not be empty
        assert exc.status_code == 500

    def test_custom_status_code_override(self):
        exc = APIError(ErrorCode.NOT_FOUND, detail="Gone", status_code=410)
        assert exc.status_code == 410

    def test_extra_fields(self):
        exc = APIError(ErrorCode.VALIDATION_ERROR, extra={"field": "age"})
        assert exc.extra == {"field": "age"}

    def test_str_representation(self):
        exc = APIError(ErrorCode.TOKEN_EXPIRED, detail="Token expired")
        assert "[TOKEN_EXPIRED]" in str(exc)


class TestBuildErrorResponse:
    """Verify build_error_response returns correct shape."""

    def test_minimal_body(self):
        body = build_error_response(ErrorCode.NOT_FOUND, "Not found", 404)
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Not found"
        assert body["error"]["status_code"] == 404
        assert "extra" not in body["error"]

    def test_with_extra(self):
        body = build_error_response(
            ErrorCode.RATE_LIMIT_EXCEEDED, "Too fast", 429, extra={"retry_after": 30}
        )
        assert body["error"]["extra"]["retry_after"] == 30


# ── Integration Tests ───────────────────────────────────────────────────────

@pytest.fixture
def app():
    """Create a minimal FastAPI app with StructuredErrorMiddleware for testing."""
    app = FastAPI()
    app.add_middleware(StructuredErrorMiddleware)

    @app.get("/agents/{agent_id}")
    async def get_agent(agent_id: int):
        if agent_id != 1:
            raise APIError(ErrorCode.AGENT_NOT_FOUND, detail="Agent not found")
        return {"id": agent_id, "name": "test-agent"}

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: int):
        if task_id != 1:
            raise APIError(ErrorCode.TASK_NOT_FOUND, detail="Task not found")
        return {"id": task_id, "title": "test-task"}

    @app.get("/forbidden")
    async def forbidden():
        raise APIError(ErrorCode.FORBIDDEN, detail="Access denied")

    @app.get("/crash")
    async def crash():
        raise RuntimeError("unexpected")

    @app.get("/validate")
    async def validate():
        raise APIError(ErrorCode.VALIDATION_ERROR, detail="Invalid input")

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestMiddlewareIntegration:
    """Verify middleware catches APIError and returns structured JSON."""

    def test_agent_not_found_returns_structured_json(self, client):
        resp = client.get("/agents/999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "AGENT_NOT_FOUND"
        assert body["error"]["status_code"] == 404

    def test_task_not_found_returns_structured_json(self, client):
        resp = client.get("/tasks/999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "TASK_NOT_FOUND"

    def test_forbidden_returns_correct_status(self, client):
        resp = client.get("/forbidden")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["code"] == "FORBIDDEN"

    def test_validation_error_status(self, client):
        resp = client.get("/validate")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_successful_response_not_affected(self, client):
        resp = client.get("/agents/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1

    def test_unhandled_exception_becomes_internal_error(self, client):
        resp = client.get("/crash")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"

    def test_error_response_has_standard_schema(self, client):
        """Every error response must have code, message, and status_code."""
        resp = client.get("/agents/999")
        body = resp.json()
        err = body["error"]
        assert "code" in err
        assert "message" in err
        assert "status_code" in err
