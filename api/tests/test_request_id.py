"""
Tests for the request ID middleware.

Verifies:
- UUID is generated when no X-Request-ID header provided
- Client-provided X-Request-ID is preserved
- X-Request-ID is set on the response
- request_id is available in request.state
"""
import uuid
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from api.middleware.request_id import RequestIDMiddleware


@pytest.fixture
def app():
    """Create a minimal FastAPI app with the request ID middleware."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "message": "ok",
            "request_id": request.state.request_id,
        }

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRequestIDGenerated:
    """When no X-Request-ID header is provided."""

    def test_generates_uuid(self, client):
        """Should generate a UUID v4 when no header is present."""
        response = client.get("/test")
        assert response.status_code == 200
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        # Verify it's a valid UUID
        uuid.UUID(request_id)

    def test_response_body_includes_request_id(self, client):
        """The endpoint should echo back the generated request_id."""
        response = client.get("/test")
        data = response.json()
        assert "request_id" in data
        # Body request_id should match header
        assert data["request_id"] == response.headers["X-Request-ID"]

    def test_unique_per_request(self, client):
        """Each request should get a unique request ID."""
        ids = set()
        for _ in range(5):
            response = client.get("/test")
            ids.add(response.headers["X-Request-ID"])
        assert len(ids) == 5


class TestClientProvidedRequestID:
    """When the client provides an X-Request-ID header."""

    def test_preserves_client_id(self, client):
        """Should echo back the client-provided request ID."""
        my_id = "trace-abc-123"
        response = client.get("/test", headers={"X-Request-ID": my_id})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == my_id

    def test_client_id_in_body(self, client):
        """The request_id in response body should match the client header."""
        my_id = "distributed-trace-xyz"
        response = client.get("/test", headers={"X-Request-ID": my_id})
        data = response.json()
        assert data["request_id"] == my_id

    def test_multiple_requests_same_id(self, client):
        """Consecutive requests with the same header keep the same ID."""
        my_id = "correlation-id-1"
        for _ in range(3):
            response = client.get("/test", headers={"X-Request-ID": my_id})
            assert response.headers["X-Request-ID"] == my_id


class TestHeaderFormat:
    """Edge cases for header values."""

    def test_empty_string_header(self, client):
        """An empty X-Request-ID should trigger UUID generation."""
        response = client.get("/test", headers={"X-Request-ID": ""})
        assert response.status_code == 200
        # Empty string is falsy, so a new UUID should be generated
        request_id = response.headers.get("X-Request-ID")
        assert request_id
        uuid.UUID(request_id)  # Should be a valid UUID
        assert request_id != ""

    def test_non_uuid_string(self, client):
        """Non-UUID ASCII strings should be accepted as-is for distributed tracing."""
        my_id = "trace-parent-span-001"
        response = client.get("/test", headers={"X-Request-ID": my_id})
        assert response.headers["X-Request-ID"] == my_id

    def test_long_request_id(self, client):
        """Long request IDs (e.g., W3C traceparent format) should be preserved."""
        my_id = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        response = client.get("/test", headers={"X-Request-ID": my_id})
        assert response.headers["X-Request-ID"] == my_id
