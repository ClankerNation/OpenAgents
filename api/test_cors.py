"""
Tests for CORS configuration in the OpenAgents API.
"""

import os
import pytest
from fastapi.testclient import TestClient


def _make_app(origins: str = ""):
    """Create a fresh app with the given ALLOWED_ORIGINS env var."""
    os.environ["ALLOWED_ORIGINS"] = origins
    # Re-import to pick up the new env var
    import importlib
    import api.main as main_module
    importlib.reload(main_module)
    return main_module.app


class TestCORSDisabled:
    """When ALLOWED_ORIGINS is unset, CORS headers should be absent."""

    def test_no_cors_headers_without_env(self):
        os.environ.pop("ALLOWED_ORIGINS", None)
        import importlib
        import api.main as main_module
        importlib.reload(main_module)
        client = TestClient(main_module.app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers


class TestCORSWildcard:
    """When ALLOWED_ORIGINS=*, all origins should be allowed."""

    def test_wildcard_origin(self):
        app = _make_app("*")
        client = TestClient(app)
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://any-domain.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "*"

    def test_credentials_not_allowed_with_wildcard(self):
        app = _make_app("*")
        client = TestClient(app)
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://any-domain.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # With wildcard origins, credentials must be False per CORS spec
        assert "access-control-allow-credentials" not in resp.headers or \
               resp.headers.get("access-control-allow-credentials") != "true"


class TestCORSSpecificOrigins:
    """When ALLOWED_ORIGINS lists specific origins, only those should be allowed."""

    def test_allowed_origin(self):
        app = _make_app("https://app.example.com,https://admin.example.com")
        client = TestClient(app)
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"

    def test_credentials_allowed_with_specific_origins(self):
        app = _make_app("https://app.example.com")
        client = TestClient(app)
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_disallowed_origin(self):
        app = _make_app("https://app.example.com")
        client = TestClient(app)
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Disallowed origin should not get CORS headers
        assert resp.headers.get("access-control-allow-origin") != "https://evil.com"


class TestCORSMethods:
    """Verify allowed methods are exposed."""

    def test_preflight_options(self):
        app = _make_app("*")
        client = TestClient(app)
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert resp.status_code == 200
        allow_methods = resp.headers.get("access-control-allow-methods", "")
        for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS"]:
            assert method in allow_methods

    def test_cross_origin_get(self):
        app = _make_app("https://frontend.example.com")
        client = TestClient(app)
        resp = client.get(
            "/health",
            headers={"Origin": "https://frontend.example.com"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "https://frontend.example.com"
