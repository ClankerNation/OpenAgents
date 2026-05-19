"""Tests for CORS middleware (issue #121)."""

import os
import sys
import pytest
from unittest import mock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCORSMiddleware:
    def test_preflight_returns_200(self):
        """OPTIONS preflight must return 200 with CORS headers."""
        import main as _main  # noqa - module-level side effects are deliberate
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": "http://example.com"}):
            from importlib import reload
            reload(_main)
            client = TestClient(_main.app)

            resp = client.options(
                "/agents",
                headers={
                    "Origin": "http://example.com",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            )
            assert resp.status_code == 200
            assert resp.headers.get("access-control-allow-origin") == "http://example.com"
            assert "GET" in resp.headers.get("access-control-allow-methods", "")
            assert "Authorization" in resp.headers.get("access-control-allow-headers", "")

    def test_allowed_origin_gets_header(self):
        """Response to allowed origin includes CORS header."""
        import main as _main
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": "http://app.local"}):
            from importlib import reload
            reload(_main)
            client = TestClient(_main.app)

            resp = client.get("/health", headers={"Origin": "http://app.local"})
            assert resp.status_code == 200
            assert resp.headers.get("access-control-allow-origin") == "http://app.local"

    def test_disallowed_origin_no_header(self):
        """Response to disallowed origin must NOT include allow-origin."""
        import main as _main
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": "http://app.local"}):
            from importlib import reload
            reload(_main)
            client = TestClient(_main.app)

            resp = client.get("/health", headers={"Origin": "http://evil.com"})
            assert resp.status_code == 200
            assert "access-control-allow-origin" not in resp.headers

    def test_credentials_header(self):
        """Access-Control-Allow-Credentials must be present."""
        import main as _main
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": "http://app.local"}):
            from importlib import reload
            reload(_main)
            client = TestClient(_main.app)

            resp = client.get("/health", headers={"Origin": "http://app.local"})
            assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_configurable_from_env(self):
        """CORS_ORIGINS env var controls allowed origins."""
        import main as _main
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": "https://prod.example.com,https://staging.example.com"}):
            from importlib import reload
            reload(_main)
            client = TestClient(_main.app)

            resp = client.options(
                "/agents",
                headers={
                    "Origin": "https://prod.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert resp.status_code == 200
            assert resp.headers.get("access-control-allow-origin") == "https://prod.example.com"
