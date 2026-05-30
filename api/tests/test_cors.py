"""Tests for CORS middleware configuration on the OpenAgents API."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers — reimport the app under controlled env vars
# ---------------------------------------------------------------------------

def _make_client(**env_overrides) -> TestClient:
    """Create a fresh TestClient with the given environment variables.

    Because the CORS middleware is wired at module-import time we must
    reload ``api.main`` whenever we want to test a different env config.
    """
    import importlib
    import api.main

    with patch.dict(os.environ, env_overrides, clear=False):
        importlib.reload(api.main)
        return TestClient(api.main.app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROD_ORIGIN = "https://app.clanker.network"
DEV_ORIGIN = "http://localhost:3000"
DISALLOWED_ORIGIN = "https://evil.example.com"


@pytest.fixture()
def prod_client():
    """Client configured with an explicit production allow-list."""
    return _make_client(
        ALLOWED_ORIGINS=f"{PROD_ORIGIN},{DEV_ORIGIN}",
        APP_ENV="production",
    )


@pytest.fixture()
def dev_client():
    """Client configured for development — no explicit origins → wildcard."""
    return _make_client(
        ALLOWED_ORIGINS="",
        APP_ENV="development",
    )


@pytest.fixture()
def strict_no_origins_client():
    """Client in production mode with NO origins set (nothing should match)."""
    return _make_client(
        ALLOWED_ORIGINS="",
        APP_ENV="production",
    )


# ---------------------------------------------------------------------------
# Production mode — explicit origin list
# ---------------------------------------------------------------------------

class TestProductionCORS:
    """CORS behaviour when ALLOWED_ORIGINS is set and APP_ENV=production."""

    def test_allowed_origin_reflected(self, prod_client: TestClient):
        """A GET from an allowed origin receives the correct ACAO header."""
        resp = prod_client.get("/health", headers={"Origin": PROD_ORIGIN})
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == PROD_ORIGIN

    def test_credentials_enabled(self, prod_client: TestClient):
        """Production mode must send Access-Control-Allow-Credentials: true."""
        resp = prod_client.get("/health", headers={"Origin": PROD_ORIGIN})
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_disallowed_origin_rejected(self, prod_client: TestClient):
        """An origin NOT in the allow-list must NOT receive ACAO."""
        resp = prod_client.get("/health", headers={"Origin": DISALLOWED_ORIGIN})
        assert "access-control-allow-origin" not in resp.headers

    def test_preflight_options(self, prod_client: TestClient):
        """A valid preflight request returns 200 with the expected headers."""
        resp = prod_client.options(
            "/health",
            headers={
                "Origin": PROD_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == PROD_ORIGIN
        # Verify allowed methods include the requested one
        allowed_methods = resp.headers.get("access-control-allow-methods", "")
        assert "POST" in allowed_methods

    def test_preflight_includes_custom_headers(self, prod_client: TestClient):
        """Preflight must echo back allowed custom headers."""
        resp = prod_client.options(
            "/health",
            headers={
                "Origin": PROD_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Requested-With",
            },
        )
        allowed_headers = resp.headers.get("access-control-allow-headers", "")
        assert "x-requested-with" in allowed_headers.lower()


# ---------------------------------------------------------------------------
# Development mode — wildcard fall-back
# ---------------------------------------------------------------------------

class TestDevelopmentCORS:
    """CORS behaviour when APP_ENV=development and no origins are set."""

    def test_wildcard_origin(self, dev_client: TestClient):
        """Development mode must reflect '*' for any origin."""
        resp = dev_client.get("/health", headers={"Origin": "http://anything.test"})
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "*"

    def test_credentials_disabled(self, dev_client: TestClient):
        """Wildcard mode MUST NOT set credentials to avoid FastAPI crash."""
        resp = dev_client.get("/health", headers={"Origin": "http://anything.test"})
        # When credentials are disabled the header is absent
        assert resp.headers.get("access-control-allow-credentials") != "true"

    def test_preflight_in_dev_mode(self, dev_client: TestClient):
        """Preflight against the wildcard config should still succeed."""
        resp = dev_client.options(
            "/health",
            headers={
                "Origin": "http://anything.test",
                "Access-Control-Request-Method": "DELETE",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "*"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestCORSEdgeCases:
    """Miscellaneous edge-case scenarios."""

    def test_no_origin_header(self, prod_client: TestClient):
        """Requests without an Origin header should still succeed (same-origin)."""
        resp = prod_client.get("/health")
        assert resp.status_code == 200
        # No ACAO header expected when Origin is absent
        assert "access-control-allow-origin" not in resp.headers

    def test_production_no_origins_blocks_all(self, strict_no_origins_client: TestClient):
        """When production has an empty allow-list, no origin should pass."""
        resp = strict_no_origins_client.get(
            "/health", headers={"Origin": "https://any.site"}
        )
        assert "access-control-allow-origin" not in resp.headers

    def test_whitespace_in_origins_env(self):
        """Whitespace and trailing commas in ALLOWED_ORIGINS are cleaned."""
        client = _make_client(
            ALLOWED_ORIGINS=f"  {PROD_ORIGIN}  ,  , {DEV_ORIGIN}  ,",
            APP_ENV="production",
        )
        resp = client.get("/health", headers={"Origin": PROD_ORIGIN})
        assert resp.headers["access-control-allow-origin"] == PROD_ORIGIN
