"""
Tests for the request ID middleware — verifies that every response carries a
unique X-Request-ID header, that the value is a valid UUID v4, and that
different requests receive distinct IDs.
"""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from api.main import app


class TestRequestIdMiddleware:
    """Suite for the X-Request-ID request ID middleware."""

    @pytest.mark.asyncio
    async def test_health_returns_request_id(self):
        """The /health endpoint should echo back the request ID."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            body = resp.json()
            assert "request_id" in body, "/health should include request_id in response body"
            parsed = uuid.UUID(body["request_id"])
            assert parsed.version == 4, "request_id must be UUID v4"

    @pytest.mark.asyncio
    async def test_x_request_id_header_present(self):
        """Every response should include the X-Request-ID header."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert "x-request-id" in resp.headers, "Response must have X-Request-ID header"
            val = resp.headers["x-request-id"]
            parsed = uuid.UUID(val)
            assert parsed.version == 4, "X-Request-ID must be a valid UUID v4"

    @pytest.mark.asyncio
    async def test_unique_ids_per_request(self):
        """Each request should get a different request ID."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ids = set()
            for _ in range(10):
                resp = await client.get("/health")
                ids.add(resp.headers["x-request-id"])
            assert len(ids) == 10, "All 10 requests must have unique request IDs"

    @pytest.mark.asyncio
    async def test_middleware_applies_to_all_routes(self):
        """X-Request-ID should be present on all endpoint responses, not just /health."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for path in ("/health", "/agents", "/tasks", "/leaderboard"):
                resp = await client.get(path)
                assert "x-request-id" in resp.headers, f"{path} should have X-Request-ID"
                uuid.UUID(resp.headers["x-request-id"])  # must not raise

    @pytest.mark.asyncio
    async def test_request_state_accessible(self):
        """request.state.request_id should match between header and body."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            body = resp.json()
            assert uuid.UUID(body["request_id"]).version == 4
            assert resp.headers["x-request-id"] == body["request_id"], \
                "Header request_id must match body request_id"

    @pytest.mark.asyncio
    async def test_invalid_routes_get_request_id(self):
        """Even 404 responses should carry X-Request-ID."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/nonexistent")
            assert resp.status_code == 404
            assert "x-request-id" in resp.headers
            uuid.UUID(resp.headers["x-request-id"])  # must not raise
