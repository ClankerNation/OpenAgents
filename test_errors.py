"""
Tests for structured error handling.

@fix-author OWL (Bounty Brain agent)
@date 2026-06-16
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, validator
from api.errors import (
    APIError,
    NotFoundError,
    AuthError,
    ForbiddenError,
    ValidationError,
    ERROR_CODES,
    create_error_response,
    RequestIDMiddleware,
    api_error_handler,
    validation_error_handler,
    generic_error_handler,
)


class TestErrorCodes:
    def test_all_error_codes_defined(self):
        expected = {"VALIDATION_ERROR", "NOT_FOUND", "AUTH_FAILED", "FORBIDDEN", "RATE_LIMITED", "INTERNAL_ERROR"}
        assert set(ERROR_CODES.keys()) == expected

    def test_validation_error_is_400(self):
        assert ERROR_CODES["VALIDATION_ERROR"]["status"] == 400

    def test_not_found_is_404(self):
        assert ERROR_CODES["NOT_FOUND"]["status"] == 404

    def test_auth_failed_is_401(self):
        assert ERROR_CODES["AUTH_FAILED"]["status"] == 401

    def test_forbidden_is_403(self):
        assert ERROR_CODES["FORBIDDEN"]["status"] == 403

    def test_rate_limited_is_429(self):
        assert ERROR_CODES["RATE_LIMITED"]["status"] == 429

    def test_internal_error_is_500(self):
        assert ERROR_CODES["INTERNAL_ERROR"]["status"] == 500


class TestAPIError:
    def test_basic_error(self):
        err = APIError("NOT_FOUND", "Agent not 123")
        assert err.code == "NOT_FOUND"
        assert err.status == 404
        assert err.details == {}

    def test_error_with_details(self):
        err = APIError("NOT_FOUND", "Agent not found", {"resource": "Agent", "id": "42"})
        assert err.details == {"resource": "Agent", "id": "42"}

    def test_error_default_message(self):
        err = APIError("NOT_FOUND")
        assert err.message == "Resource not found"


class TestNotFound:
    def test_not_found_error(self):
        err = NotFoundError("Agent", 42)
        assert err.code == "NOT_FOUND"
        assert err.status == 404
        assert err.details["resource"] == "Agent"
        assert err.details["id"] == "42"

    def test_not_found_no_id(self):
        err = NotFoundError("Task")
        assert "id" not in err.details


class TestAuthError:
    def test_auth_error_default(self):
        err = AuthError()
        assert err.code == "AUTH_FAILED"
        assert err.status == 401

    def test_auth_error_custom_message(self):
        err = AuthError("Token expired")
        assert err.message == "Token expired"


class TestForbidden:
    def test_forbidden_default(self):
        err = ForbiddenError()
        assert err.code == "FORBIDDEN"
        assert err.status == 403


class TestErrorSchema:
    def _body_json(self, resp):
        """Safely decode JSON response body."""
        return resp.json()

    def test_error_response_has_code(self):
        resp = create_error_response("NOT_FOUND", "Not found", 404)
        data = self._body_json(resp)
        assert "code" in data
        assert data["code"] == "NOT_FOUND"

    def test_error_response_has_message(self):
        resp = create_error_response("NOT_FOUND", "Agent not found", 404)
        data = self._body_json(resp)
        assert data["message"] == "Agent not found"

    def test_error_response_has_details(self):
        resp = create_error_response("NOT_FOUND", "Not found", 404, {"resource": "Agent"})
        data = self._body_json(resp)
        assert "details" in data
        assert data["details"]["resource"] == "Agent"

    def test_error_response_has_request_id(self):
        resp = create_error_response("NOT_FOUND", "Not found", 404, {}, request_id="req-123")
        data = self._body_json(resp)
        assert data["request_id"] == "req-123"

    def test_error_response_without_request_id(self):
        resp = create_error_response("NOT_FOUND", "Not found", 404)
        data = self._body_json(resp)
        assert "request_id" not in data


class TestIntegration:
    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)
        app.add_exception_handler(APIError, api_error_handler)
        app.add_exception_handler(RequestValidationError, validation_error_handler)
        app.add_exception_handler(Exception, generic_error_handler)

        class Item(BaseModel):
            name: str
            price: float

            @validator("price")
            def price_must_be_positive(cls, v):
                if v <= 0:
                    raise ValueError("Price must be positive")
                return v

        @app.get("/items/{item_id}")
        async def get_item(item_id: int):
            raise NotFoundError("Item", item_id)

        @app.post("/items")
        async def create_item(item: Item):
            return item

        @app.get("/auth-test")
        async def auth_test():
            raise AuthError()

        @app.get("/forbidden-test")
        async def forbidden_test():
            raise ForbiddenError("Admin access required")

        @app.get("/error-test")
        async def error_test():
            raise RuntimeError("Something broke")

        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app, raise_server_exceptions=False)

    def test_not_found_returns_structured_response(self, client):
        response = client.get("/items/999")
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "NOT_FOUND"
        assert data["message"] == "Item not found"
        assert data["details"]["resource"] == "Item"

    def test_auth_error_returns_structured_response(self, client):
        response = client.get("/auth-test")
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "AUTH_FAILED"

    def test_forbidden_returns_structured_response(self, client):
        response = client.get("/forbidden-test")
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "FORBIDDEN"
        assert "Admin" in data["message"]

    def test_validation_error_has_field_details(self, client):
        response = client.post("/items", json={"name": "", "price": -1})
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "VALIDATION_ERROR"
        assert "fields" in data["details"]

    def test_generic_error_returns_500(self, client):
        response = client.get("/error-test")
        assert response.status_code == 500
        data = response.json()
        assert data["code"] == "INTERNAL_ERROR"
        # Should NOT leak internal details
        assert "broke" not in data["message"].lower()

    def test_request_id_in_success_response(self, client):
        """Request ID should appear in all responses."""
        response = client.get("/items/999")
        assert "X-Request-ID" in response.headers
        # Body should also have it for errors
        data = response.json()
        assert "request_id" in data

    def test_client_can_provide_request_id(self, client):
        """Client-provided X-Request-ID should be echoed back."""
        response = client.get("/items/999", headers={"X-Request-ID": "my-req-123"})
        assert response.headers["X-Request-ID"] == "my-req-123"
        data = response.json()
        assert data["request_id"] == "my-req-123"

    def test_error_response_status_codes(self, client):
        """Error response status code should match the error type."""
        assert client.get("/items/999").status_code == 404
        assert client.get("/auth-test").status_code == 401
        assert client.get("/error-test").status_code == 500
