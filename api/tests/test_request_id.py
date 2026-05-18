"""
Tests for Request-ID middleware on the OpenAgents API.

Covers:
  - X-Request-ID response header is always present
  - Auto-generated UUIDs are valid and unique across requests
  - Client-provided X-Request-ID is passed through unchanged
  - Request ID is included in log output for correlation
"""

import importlib
import logging
import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    """Fresh TestClient against the app module."""
    import api.main as _main

    importlib.reload(_main)
    return TestClient(_main.app)


# ---------------------------------------------------------------------------
# 1. Header presence – every response must carry X-Request-ID
# ---------------------------------------------------------------------------
class TestHeaderPresence:
    """Verify the X-Request-ID header is always returned."""

    def test_health_endpoint_has_request_id(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_agents_endpoint_has_request_id(self, client):
        resp = client.get("/agents")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_tasks_endpoint_has_request_id(self, client):
        resp = client.get("/tasks")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_404_endpoint_has_request_id(self, client):
        resp = client.get("/agents/nonexistent")
        # 404, but still must have request ID header
        assert "x-request-id" in resp.headers


# ---------------------------------------------------------------------------
# 2. Client ID pass-through – distributed tracing
# ---------------------------------------------------------------------------
class TestClientPassThrough:
    """Verify that a client-supplied X-Request-ID is echoed back."""

    def test_client_id_returned_verbatim(self, client):
        custom_id = "my-trace-12345"
        resp = client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers["x-request-id"] == custom_id

    def test_client_uuid_returned(self, client):
        custom_uuid = str(uuid.uuid4())
        resp = client.get("/health", headers={"X-Request-ID": custom_uuid})
        assert resp.headers["x-request-id"] == custom_uuid

    def test_long_client_id_returned(self, client):
        long_id = "a" * 256
        resp = client.get("/health", headers={"X-Request-ID": long_id})
        assert resp.headers["x-request-id"] == long_id


# ---------------------------------------------------------------------------
# 3. Uniqueness – auto-generated IDs must be unique
# ---------------------------------------------------------------------------
class TestUniqueness:
    """Verify auto-generated request IDs are unique UUIDs."""

    def test_two_requests_different_ids(self, client):
        id1 = client.get("/health").headers["x-request-id"]
        id2 = client.get("/health").headers["x-request-id"]
        assert id1 != id2

    def test_auto_id_is_valid_uuid4(self, client):
        # Don't pass X-Request-ID so the middleware generates one
        resp = client.get("/health")
        rid = resp.headers["x-request-id"]
        # uuid4 format: 8-4-4-4-12 hex chars
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        assert uuid_pattern.match(rid), f"Generated ID {rid!r} is not a valid UUID4"

    def test_many_requests_all_unique(self, client):
        ids = set()
        for _ in range(50):
            rid = client.get("/health").headers["x-request-id"]
            ids.add(rid)
        assert len(ids) == 50, "Generated IDs were not all unique"


# ---------------------------------------------------------------------------
# 4. Log correlation – request ID appears in log output
# ---------------------------------------------------------------------------
class TestLogCorrelation:
    """Verify that log messages include the request ID."""

    def test_request_id_in_log_records(self, client):
        import api.main as _main

        captured = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record)

        handler = CaptureHandler()
        handler.addFilter(_main.RequestIdFilter())
        _main._logger.addHandler(handler)

        try:
            rid = "log-correlation-test-id-999"
            resp = client.get("/health", headers={"X-Request-ID": rid})
            assert resp.status_code == 200

            # At least one log record should carry our request_id
            matching = [r for r in captured if getattr(r, "request_id", None) == rid]
            assert len(matching) >= 1, (
                f"Expected request_id={rid!r} in log records, "
                f"got: {[getattr(r, 'request_id', None) for r in captured]}"
            )
        finally:
            _main._logger.removeHandler(handler)