"""Tests for request ID middleware."""

import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.request_id import RequestIDMiddleware


def make_app():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    return app


class TestRequestIDMiddleware:
    def test_generates_uuid_when_no_header(self):
        client = TestClient(make_app())
        response = client.get("/test")
        assert response.status_code == 200
        req_id = response.headers.get("X-Request-ID")
        assert req_id is not None
        # Should be a valid UUID
        uuid.UUID(req_id)

    def test_preserves_client_provided_id(self):
        client = TestClient(make_app())
        custom_id = "my-trace-id-12345"
        response = client.get("/test", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id

    def test_unique_ids_per_request(self):
        client = TestClient(make_app())
        ids = set()
        for _ in range(10):
            response = client.get("/test")
            ids.add(response.headers["X-Request-ID"])
        assert len(ids) == 10

    def test_header_present_on_error(self):
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/fail")
        async def fail():
            raise ValueError("boom")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/fail")
        assert "X-Request-ID" in response.headers
