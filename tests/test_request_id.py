import pytest
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.request_id import (
    RequestIDMiddleware, RequestIDLogFilter, get_request_id,
    REQUEST_ID_HEADER, setup_request_id_logging,
)


class TestRequestIDMiddleware:
    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"request_id": get_request_id(), "ok": True}

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        return app

    def test_response_has_request_id_header(self, app):
        client = TestClient(app)
        resp = client.get("/test")
        assert REQUEST_ID_HEADER in resp.headers
        request_id = resp.headers[REQUEST_ID_HEADER]
        assert uuid.UUID(request_id)

    def test_request_id_in_response_body(self, app):
        client = TestClient(app)
        resp = client.get("/test")
        data = resp.json()
        assert data["request_id"] == resp.headers[REQUEST_ID_HEADER]

    def test_client_supplied_request_id_is_used(self, app):
        client = TestClient(app)
        custom_id = "my-custom-trace-id-123"
        resp = client.get("/test", headers={REQUEST_ID_HEADER: custom_id})
        assert resp.headers[REQUEST_ID_HEADER] == custom_id
        assert resp.json()["request_id"] == custom_id

    def test_request_id_is_unique_per_request(self, app):
        client = TestClient(app)
        resp1 = client.get("/test")
        resp2 = client.get("/test")
        assert resp1.headers[REQUEST_ID_HEADER] != resp2.headers[REQUEST_ID_HEADER]

    def test_health_also_gets_request_id(self, app):
        client = TestClient(app)
        resp = client.get("/health")
        assert REQUEST_ID_HEADER in resp.headers
        assert uuid.UUID(resp.headers[REQUEST_ID_HEADER])

    def test_multiple_paths_same_request_id(self, app):
        client = TestClient(app)
        custom_id = "multi-path-test"
        resp1 = client.get("/test", headers={REQUEST_ID_HEADER: custom_id})
        resp2 = client.get("/health", headers={REQUEST_ID_HEADER: custom_id})
        assert resp1.headers[REQUEST_ID_HEADER] == custom_id
        assert resp2.headers[REQUEST_ID_HEADER] == custom_id

    def test_request_id_is_valid_uuid_when_not_provided(self, app):
        client = TestClient(app)
        resp = client.get("/test")
        rid = resp.headers[REQUEST_ID_HEADER]
        assert uuid.UUID(rid, version=4)


class TestRequestIDLogFilter:
    def test_filter_adds_request_id(self):
        import logging
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)
        setup_request_id_logging()

        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", None, None)
        f = RequestIDLogFilter()
        f.request_id = "test-123"
        assert f.filter(record)
        assert record.request_id == "test-123"

    def test_filter_default_dash(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", None, None)
        f = RequestIDLogFilter()
        assert f.filter(record)
        assert record.request_id == "-"
