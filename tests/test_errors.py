import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.middleware.errors import (
    ErrorCode, AppHTTPException, error_response,
    app_exception_handler, http_exception_handler,
    validation_exception_handler, general_exception_handler,
)


class TestErrorResponseFormat:
    def test_error_response_structure(self):
        resp = error_response(ErrorCode.NOT_FOUND, "Agent not found")
        assert resp == {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Agent not found"},
        }

    def test_error_response_with_details(self):
        resp = error_response(ErrorCode.INVALID_INPUT, "Bad input", {"field": "name"})
        assert resp["success"] is False
        assert resp["error"]["code"] == "INVALID_INPUT"
        assert resp["error"]["details"] == {"field": "name"}

    def test_all_error_codes_have_status(self):
        from api.middleware.errors import ERROR_STATUS_MAP
        for code in ErrorCode:
            assert code in ERROR_STATUS_MAP, f"{code} missing from status map"


class TestAppHTTPException:
    def test_app_exception_creates_response(self):
        exc = AppHTTPException(ErrorCode.NOT_FOUND, "Test not found")
        assert exc.status_code == 404
        assert exc.detail["success"] is False
        assert exc.detail["error"]["code"] == "NOT_FOUND"

    def test_forbidden_exception(self):
        exc = AppHTTPException(ErrorCode.FORBIDDEN, "Access denied")
        assert exc.status_code == 403
        assert exc.detail["error"]["code"] == "FORBIDDEN"

    def test_validation_exception(self):
        exc = AppHTTPException(ErrorCode.VALIDATION_ERROR, "Invalid")
        assert exc.status_code == 400
        assert exc.detail["error"]["code"] == "VALIDATION_ERROR"

    def test_auth_exception(self):
        exc = AppHTTPException(ErrorCode.AUTH_ERROR, "Bad token")
        assert exc.status_code == 401
        assert exc.detail["error"]["code"] == "AUTH_ERROR"


class TestErrorHandlers:

    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.add_exception_handler(AppHTTPException, app_exception_handler)
        app.add_exception_handler(HTTPException, http_exception_handler)
        app.add_exception_handler(RequestValidationError, validation_exception_handler)
        app.add_exception_handler(Exception, general_exception_handler)

        @app.get("/test-not-found")
        async def test_not_found():
            raise AppHTTPException(ErrorCode.NOT_FOUND, "Item missing")

        @app.get("/test-forbidden")
        async def test_forbidden():
            raise AppHTTPException(ErrorCode.FORBIDDEN, "No access")

        @app.get("/test-http-404")
        async def test_http_404():
            raise HTTPException(status_code=404, detail="Old style not found")

        @app.get("/test-internal")
        async def test_internal():
            raise RuntimeError("Unexpected crash")

        return app

    def test_app_http_exception_format(self, app):
        client = TestClient(app)
        resp = client.get("/test-not-found")
        assert resp.status_code == 404
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["message"] == "Item missing"

    def test_forbidden_format(self, app):
        client = TestClient(app)
        resp = client.get("/test-forbidden")
        assert resp.status_code == 403
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "FORBIDDEN"

    def test_legacy_http_exception_converted(self, app):
        client = TestClient(app)
        resp = client.get("/test-http-404")
        assert resp.status_code == 404
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"

    def test_unhandled_exception(self, app):
        client = TestClient(app)
        resp = client.get("/test-internal")
        assert resp.status_code == 500
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"


class TestErrorCodesEnum:
    def test_all_expected_codes_present(self):
        expected = [
            "VALIDATION_ERROR", "AUTH_ERROR", "NOT_FOUND", "FORBIDDEN",
            "RATE_LIMIT", "CONFLICT", "INTERNAL_ERROR", "INVALID_INPUT",
            "DUPLICATE_ENTRY", "PAYMENT_ERROR", "TASK_ERROR", "AGENT_ERROR",
        ]
        for code in expected:
            assert ErrorCode(code) is not None
