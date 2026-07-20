"""Tests for CORS middleware, request ID middleware, and app configuration."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestCORS:
    def test_cors_headers_present(self):
        resp = client.get("/health", headers={"Origin": "http://example.com"})
        origin = resp.headers.get("access-control-allow-origin", "")
        assert origin == "http://example.com" or origin == "*"
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_cors_allow_methods(self):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200
        assert "POST" in resp.headers.get("access-control-allow-methods", "")


class TestRequestID:
    def test_request_id_header_present(self):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) > 0

    def test_request_id_unique_per_request(self):
        resp1 = client.get("/health")
        resp2 = client.get("/health")
        assert resp1.headers["X-Request-ID"] != resp2.headers["X-Request-ID"]
