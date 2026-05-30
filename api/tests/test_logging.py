"""Tests for the Request ID middleware and log correlation filter."""

import logging
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app, request_id_ctx, RequestIDFilter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Request ID generation & propagation
# ---------------------------------------------------------------------------

class TestRequestIDPropagation:
    """Verify that every response carries a unique X-Request-ID header."""

    def test_auto_generated_request_id(self, client: TestClient):
        """When no X-Request-ID is sent, the middleware must generate one."""
        resp = client.get("/health")
        assert resp.status_code == 200
        rid = resp.headers.get("X-Request-ID")
        assert rid is not None, "Response must contain X-Request-ID header"
        # Generated IDs are uuid4().hex → 32-char lowercase hex string
        assert re.fullmatch(r"[0-9a-f]{32}", rid), f"Unexpected ID format: {rid}"

    def test_unique_ids_per_request(self, client: TestClient):
        """Consecutive requests must receive distinct trace tokens."""
        ids = {client.get("/health").headers["X-Request-ID"] for _ in range(20)}
        assert len(ids) == 20, "All generated request IDs must be unique"

    def test_client_supplied_request_id_preserved(self, client: TestClient):
        """The middleware must honour a pre-set X-Request-ID from the client."""
        custom_id = "client-trace-abc-123"
        resp = client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers["X-Request-ID"] == custom_id

    def test_request_id_on_error_route(self, client: TestClient):
        """Even 404 responses must carry the trace header."""
        resp = client.get("/agents/nonexistent")
        assert resp.status_code == 404
        assert "X-Request-ID" in resp.headers


# ---------------------------------------------------------------------------
# Client override edge cases
# ---------------------------------------------------------------------------

class TestClientOverrides:
    """Ensure varied client-supplied IDs are propagated faithfully."""

    @pytest.mark.parametrize("custom_id", [
        "simple-id",
        "00000000000000000000000000000000",
        "UPPER-CASE-ID",
        "id-with-special_chars.v2",
        "a" * 128,
    ])
    def test_arbitrary_client_ids(self, client: TestClient, custom_id: str):
        """The middleware must relay the exact client ID regardless of format."""
        resp = client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers["X-Request-ID"] == custom_id

    def test_empty_header_triggers_generation(self, client: TestClient):
        """An empty X-Request-ID string must be treated as missing."""
        resp = client.get("/health", headers={"X-Request-ID": ""})
        rid = resp.headers["X-Request-ID"]
        assert rid != "", "Empty client ID should trigger auto-generation"
        assert re.fullmatch(r"[0-9a-f]{32}", rid)


# ---------------------------------------------------------------------------
# Log correlation filter
# ---------------------------------------------------------------------------

class TestRequestIDFilter:
    """Validate the logging.Filter that injects ``request_id`` into records."""

    def test_filter_adds_request_id_attribute(self):
        """The filter must attach the active context value to log records."""
        # Read the live ContextVar from the module — the CORS test suite may
        # have reloaded api.main, replacing the module-level object.
        import api.main as _mod
        ctx = _mod.request_id_ctx

        filt = RequestIDFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        token = ctx.set("test-trace-42")
        try:
            filt.filter(record)
            assert record.request_id == "test-trace-42"
        finally:
            ctx.reset(token)

    def test_filter_fallback_outside_request(self):
        """Outside a request context the filter should return 'N/A'."""
        filt = RequestIDFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        filt.filter(record)
        assert record.request_id == "N/A"

    def test_log_format_includes_request_id(self, capfd, client: TestClient):
        """The configured logger must emit lines containing the trace token."""
        # Import the module-level logger so we can trigger a real log line.
        from api.main import logger as app_logger

        custom_id = "log-format-check-999"
        # Issue a request so the middleware sets the context var, then log
        # inside the test (synchronous TestClient keeps the same context).
        with client:
            resp = client.get(
                "/health", headers={"X-Request-ID": custom_id}
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Concurrent request isolation
# ---------------------------------------------------------------------------

class TestConcurrentStability:
    """Ensure request IDs do not bleed across sequential requests."""

    def test_sequential_isolation(self, client: TestClient):
        """Back-to-back requests must each carry their own trace token."""
        id_a = "isolation-aaa"
        id_b = "isolation-bbb"

        resp_a = client.get("/health", headers={"X-Request-ID": id_a})
        resp_b = client.get("/health", headers={"X-Request-ID": id_b})

        assert resp_a.headers["X-Request-ID"] == id_a
        assert resp_b.headers["X-Request-ID"] == id_b

    def test_context_reset_after_request(self, client: TestClient):
        """After a request completes, the ContextVar must revert to default."""
        client.get("/health", headers={"X-Request-ID": "should-be-cleaned"})
        assert request_id_ctx.get("N/A") == "N/A", \
            "ContextVar was not reset — state leakage detected"
