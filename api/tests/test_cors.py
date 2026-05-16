"""Tests for CORS configuration in the OpenAgents API."""

import os
import pytest
from fastapi.testclient import TestClient


class TestCORSConfiguration:
    """Test CORS headers are properly configured."""

    def test_preflight_options_request(self):
        """Test preflight OPTIONS request returns correct CORS headers."""
        # Import fresh to get default config
        os.environ.pop("ALLOWED_ORIGINS", None)
        os.environ.pop("ENVIRONMENT", None)

        from importlib import reload
        import api.main
        reload(api.main)

        client = TestClient(api.main.app)

        response = client.options(
            "/health",
            headers={
                "Origin": "https://openagents.dev",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-credentials" in response.headers

    def test_cross_origin_get_request(self):
        """Test cross-origin GET request includes CORS headers."""
        os.environ.pop("ALLOWED_ORIGINS", None)
        os.environ.pop("ENVIRONMENT", None)

        from importlib import reload
        import api.main
        reload(api.main)

        client = TestClient(api.main.app)

        response = client.get(
            "/health",
            headers={"Origin": "https://openagents.dev"},
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://openagents.dev"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_credentials_allowed(self):
        """Test that credentials are allowed in CORS responses."""
        os.environ.pop("ALLOWED_ORIGINS", None)
        os.environ.pop("ENVIRONMENT", None)

        from importlib import reload
        import api.main
        reload(api.main)

        client = TestClient(api.main.app)

        response = client.get(
            "/health",
            headers={"Origin": "https://openagents.dev"},
        )

        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_custom_origins_from_env(self):
        """Test ALLOWED_ORIGINS env var configures allowed origins."""
        os.environ["ALLOWED_ORIGINS"] = "https://custom.example.com,https://another.example.com"
        os.environ.pop("ENVIRONMENT", None)

        from importlib import reload
        import api.main
        reload(api.main)

        client = TestClient(api.main.app)

        # Request from allowed origin
        response = client.get(
            "/health",
            headers={"Origin": "https://custom.example.com"},
        )
        assert response.headers.get("access-control-allow-origin") == "https://custom.example.com"

        # Cleanup
        os.environ.pop("ALLOWED_ORIGINS", None)

    def test_wildcard_only_in_development(self):
        """Test wildcard origins only work in development mode."""
        os.environ["ALLOWED_ORIGINS"] = "*"
        os.environ["ENVIRONMENT"] = "development"

        from importlib import reload
        import api.main
        reload(api.main)

        client = TestClient(api.main.app)

        response = client.get(
            "/health",
            headers={"Origin": "https://any-origin.com"},
        )

        # In development with wildcard, any origin should be allowed
        assert response.headers.get("access-control-allow-origin") == "*"

        # Cleanup
        os.environ.pop("ALLOWED_ORIGINS", None)
        os.environ.pop("ENVIRONMENT", None)

    def test_wildcard_rejected_in_production(self):
        """Test wildcard is NOT used in production mode."""
        os.environ["ALLOWED_ORIGINS"] = "*"
        os.environ["ENVIRONMENT"] = "production"

        from importlib import reload
        import api.main
        reload(api.main)

        # In production, wildcard should fall back to default restrictive list
        assert "*" not in api.main.allowed_origins

        # Cleanup
        os.environ.pop("ALLOWED_ORIGINS", None)
        os.environ.pop("ENVIRONMENT", None)

    def test_exposed_headers(self):
        """Test that custom headers are exposed in CORS responses."""
        os.environ.pop("ALLOWED_ORIGINS", None)
        os.environ.pop("ENVIRONMENT", None)

        from importlib import reload
        import api.main
        reload(api.main)

        client = TestClient(api.main.app)

        response = client.options(
            "/health",
            headers={
                "Origin": "https://openagents.dev",
                "Access-Control-Request-Method": "GET",
            },
        )

        exposed = response.headers.get("access-control-expose-headers", "")
        assert "X-Request-ID" in exposed or "x-request-id" in exposed.lower()
