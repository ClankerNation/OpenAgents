"""Tests for request ID middleware (issue #178)."""

import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestRequestIDMiddleware:
    def test_response_has_x_request_id(self):
        """Every response must include X-Request-ID header."""
        import main as _main
        from importlib import reload
        reload(_main)
        client = TestClient(_main.app)

        resp = client.get("/health")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        request_id = resp.headers["x-request-id"]
        # Must be a valid UUID
        uuid.UUID(request_id)

    def test_caller_supplied_id_preserved(self):
        """When caller sends X-Request-ID, it must be echoed back."""
        import main as _main
        from importlib import reload
        reload(_main)
        client = TestClient(_main.app)

        caller_id = "req-abc-123-test"
        resp = client.get("/health", headers={"X-Request-ID": caller_id})
        assert resp.status_code == 200
        assert resp.headers["x-request-id"] == caller_id

    def test_unique_ids_per_request(self):
        """Auto-generated IDs must be unique per request."""
        import main as _main
        from importlib import reload
        reload(_main)
        client = TestClient(_main.app)

        ids = set()
        for _ in range(10):
            resp = client.get("/health")
            ids.add(resp.headers["x-request-id"])
        assert len(ids) == 10

    def test_request_id_on_404(self):
        """Error responses must also carry X-Request-ID."""
        import main as _main
        from importlib import reload
        reload(_main)
        client = TestClient(_main.app)

        resp = client.get("/nonexistent")
        assert resp.status_code == 404
        assert "x-request-id" in resp.headers

    def test_request_id_accessible_in_state(self):
        """request.state.request_id must be set for downstream handlers."""
        import main as _main
        from fastapi import Request

        @_main.app.get("/_test_state")
        async def _test_state(request: Request):
            rid = getattr(request.state, "request_id", None)
            return {"request_id": rid}

        from importlib import reload
        # Can't reload because we just patched the app - just build fresh
        client = TestClient(_main.app)
        resp = client.get("/_test_state")
        assert resp.status_code == 200
        data = resp.json()
        assert "request_id" in data
        uuid.UUID(data["request_id"])
