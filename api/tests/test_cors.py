"""
Tests for CORS configuration on the OpenAgents API.

Covers:
  - Preflight OPTIONS requests return proper CORS headers
  - Cross-origin GET requests include Access-Control-Allow-Origin
  - Credentials header is present when origin matches allowed list
  - Wildcard origin is NOT used (restrictive defaults)
  - Custom ALLOWED_ORIGINS env var is respected
"""

import os
import importlib
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper: rebuild the app module so env-var changes take effect
# ---------------------------------------------------------------------------
def _import_app_with_origins(origins_env: str):
    """Set ALLOWED_ORIGINS, reimport main, return (app, _allowed_origins)."""
    os.environ["ALLOWED_ORIGINS"] = origins_env
    # Force reimport so the module-level env read is re-evaluated
    import api.main as _main

    importlib.reload(_main)
    return _main


@pytest.fixture()
def client_default():
    """TestClient using the default (restrictive) origins."""
    os.environ.pop("ALLOWED_ORIGINS", None)
    import api.main as _main

    importlib.reload(_main)
    return TestClient(_main.app), _main._allowed_origins


@pytest.fixture()
def client_custom():
    """TestClient with an explicit custom origin."""
    _main = _import_app_with_origins("https://example.com,https://app.example.com")
    return TestClient(_main.app), _main._allowed_origins


# ---------------------------------------------------------------------------
# 1. Preflight OPTIONS requests
# ---------------------------------------------------------------------------
class TestPreflightOptions:
    """Verify that CORS preflight (OPTIONS) requests return correct headers."""

    def test_options_returns_allow_origin(self, client_default):
        client, _ = client_default
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_options_returns_allow_methods(self, client_default):
        client, _ = client_default
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS"]:
            assert method in allowed_methods, f"{method} missing from Allow-Methods"

    def test_options_returns_allow_headers(self, client_default):
        client, _ = client_default
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allowed_headers = response.headers.get("access-control-allow-headers", "")
        assert "authorization" in allowed_headers.lower()

    def test_options_rejects_unknown_origin(self, client_default):
        client, _ = client_default
        response = client.options(
            "/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI CORSMiddleware returns 400 for disallowed preflight origins
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 2. Cross-origin GET requests
# ---------------------------------------------------------------------------
class TestCrossOriginGet:
    """Verify that actual cross-origin GET requests include CORS headers."""

    def test_get_includes_allow_origin(self, client_default):
        client, _ = client_default
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_get_rejects_unknown_origin(self, client_default):
        """When the origin is not in the allowed list, no Allow-Origin header is set."""
        client, _ = client_default
        response = client.get("/health", headers={"Origin": "https://evil.example.com"})
        assert response.headers.get("access-control-allow-origin") is None

    def test_get_with_custom_origins(self, client_custom):
        client, origins = client_custom
        response = client.get("/health", headers={"Origin": "https://example.com"})
        assert response.headers.get("access-control-allow-origin") == "https://example.com"

    def test_get_health_body(self, client_default):
        """Ensure CORS headers don't interfere with normal response body."""
        client, _ = client_default
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
        data = response.json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# 3. Credentials support
# ---------------------------------------------------------------------------
class TestCredentials:
    """Verify that allow_credentials=True works correctly."""

    def test_preflight_includes_allow_credentials(self, client_default):
        client, _ = client_default
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_get_includes_allow_credentials(self, client_default):
        client, _ = client_default
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_no_wildcard_origin_in_production(self, client_custom):
        """Ensure wildcard '*' is never used in allowed origins (incompatible with credentials)."""
        _, origins = client_custom
        assert "*" not in origins, "Wildcard origin must not be used with allow_credentials=True"


# ---------------------------------------------------------------------------
# 4. Configuration from environment
# ---------------------------------------------------------------------------
class TestEnvConfiguration:
    """Verify ALLOWED_ORIGINS env var is parsed correctly."""

    def test_single_origin(self):
        _main = _import_app_with_origins("https://single.example.com")
        assert _main._allowed_origins == ["https://single.example.com"]

    def test_multiple_origins_comma_separated(self):
        _main = _import_app_with_origins("https://a.com, https://b.com,https://c.com")
        assert _main._allowed_origins == ["https://a.com", "https://b.com", "https://c.com"]

    def test_empty_env_uses_defaults(self):
        os.environ.pop("ALLOWED_ORIGINS", None)
        import api.main as _main

        importlib.reload(_main)
        assert "http://localhost:3000" in _main._allowed_origins
        assert "http://localhost:8000" in _main._allowed_origins