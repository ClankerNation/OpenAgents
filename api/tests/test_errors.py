"""Tests for standardized error responses."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from unittest.mock import patch

from api.main import app
from api.errors import ErrorCode


client = TestClient(app)


def _assert_error_response(response, expected_code: str, expected_status: int):
    assert response.status_code == expected_status
    data = response.json()
    assert "code" in data
    assert "message" in data
    assert "details" in data
    assert "request_id" in data
    assert data["code"] == expected_code
    assert isinstance(data["message"], str)
    assert len(data["message"]) > 0
    assert isinstance(data["details"], dict)
    assert isinstance(data["request_id"], str)
    assert len(data["request_id"]) > 0
    return data


class TestRequestId:
    def test_request_id_in_error_response(self):
        response = client.get("/nonexistent-path")
        data = _assert_error_response(response, ErrorCode.NOT_FOUND.value, 404)
        assert data["request_id"]

    def test_custom_request_id_header(self):
        response = client.get("/nonexistent-path", headers={"X-Request-ID": "test-123"})
        data = response.json()
        assert data["request_id"] == "test-123"

    def test_request_id_in_success_response_header(self):
        response = client.get("/health")
        assert "X-Request-ID" in response.headers


class TestNotFoundError:
    def test_nonexistent_route_returns_structured_404(self):
        response = client.get("/nonexistent-path")
        _assert_error_response(response, ErrorCode.NOT_FOUND.value, 404)


class TestValidationError:
    def test_invalid_query_param_returns_validation_error(self):
        response = client.get("/tasks/?limit=0")
        _assert_error_response(response, ErrorCode.VALIDATION_ERROR.value, 422)

    def test_validation_error_has_field_details(self):
        response = client.get("/tasks/?limit=0")
        data = response.json()
        assert "fields" in data["details"]
        fields = data["details"]["fields"]
        assert len(fields) > 0
        assert "field" in fields[0]
        assert "message" in fields[0]
        assert "type" in fields[0]


class TestAuthError:
    def test_missing_auth_header_returns_auth_error(self):
        response = client.post("/tasks/", json={"title": "test", "description": "test", "reward_amount": 10})
        _assert_error_response(response, ErrorCode.AUTH_FAILED.value, 401)

    def test_invalid_token_returns_auth_error(self):
        response = client.post(
            "/tasks/",
            json={"title": "test", "description": "test", "reward_amount": 10},
            headers={"Authorization": "Bearer invalid-token"},
        )
        _assert_error_response(response, ErrorCode.AUTH_FAILED.value, 401)


class TestInternalError:
    def test_unhandled_exception_returns_500(self):
        from starlette.routing import Route

        async def error_route(request):
            raise RuntimeError("boom")

        app.routes.append(Route("/test-error", endpoint=error_route))
        test_client = TestClient(app, raise_server_exceptions=False)
        response = test_client.get("/test-error")
        _assert_error_response(response, ErrorCode.INTERNAL_ERROR.value, 500)
        app.routes.pop()


class TestErrorCodeEnum:
    def test_all_error_codes_present(self):
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.NOT_FOUND.value == "NOT_FOUND"
        assert ErrorCode.AUTH_FAILED.value == "AUTH_FAILED"
        assert ErrorCode.RATE_LIMITED.value == "RATE_LIMITED"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"

    def test_error_codes_are_strings(self):
        for code in ErrorCode:
            assert isinstance(code.value, str)


class TestErrorSchema:
    def test_error_response_has_all_fields(self):
        response = client.get("/nonexistent-path")
        data = response.json()
        assert set(data.keys()) == {"code", "message", "details", "request_id"}

    def test_error_code_is_valid_enum(self):
        response = client.get("/nonexistent-path")
        data = response.json()
        assert data["code"] in [e.value for e in ErrorCode]
