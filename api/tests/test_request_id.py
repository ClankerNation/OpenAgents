"""Tests for request ID middleware."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


class TestRequestIdHeader:
    def test_response_has_request_id(self):
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    def test_request_id_is_uuid_format(self):
        response = client.get("/health")
        request_id = response.headers["X-Request-ID"]
        parts = request_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_each_request_gets_unique_id(self):
        r1 = client.get("/health")
        r2 = client.get("/health")
        id1 = r1.headers["X-Request-ID"]
        id2 = r2.headers["X-Request-ID"]
        assert id1 != id2

    def test_client_request_id_preserved(self):
        custom_id = "my-custom-trace-id-12345"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id

    def test_client_request_id_preserved_on_error(self):
        custom_id = "error-trace-id-67890"
        response = client.get("/nonexistent", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_on_all_endpoints(self):
        endpoints = ["/health", "/agents", "/tasks", "/leaderboard"]
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert "X-Request-ID" in response.headers, (
                f"Missing X-Request-ID on {endpoint}"
            )


class TestRequestIdLogging:
    def test_request_id_in_log_output(self, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="openagents"):
            response = client.get("/health")

        request_id = response.headers["X-Request-ID"]
        request_ids_in_logs = [
            getattr(r, "request_id", None) for r in caplog.records
        ]
        assert request_id in request_ids_in_logs
