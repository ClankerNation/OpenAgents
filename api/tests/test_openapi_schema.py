"""Tests for OpenAPI schema generation (Bounty #185).

Verifies:
- /openapi.json endpoint is available and valid
- Security schemes (JWT Bearer + API Key) are registered
- Tag metadata is present
- Error schema components exist
- Per-route documentation (summary, description, responses)
- Schema validity and required fields
"""

import sys
import os
from pathlib import Path

# Add the project root (parent of api/) so we can import as api.main
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    """Return a TestClient for the FastAPI app."""
    return TestClient(app)


# ── Schema Endpoint Tests ───────────────────────────────────────────────────


class TestOpenAPIEndpoint:
    """Verify the /openapi.json endpoint is available and returns valid JSON."""

    def test_openapi_endpoint_exists(self, client):
        """The /openapi.json endpoint must respond 200."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200

    def test_openapi_returns_valid_json(self, client):
        """Response must be parseable JSON."""
        resp = client.get("/openapi.json")
        assert resp.headers["content-type"] in (
            "application/json",
            "application/json; charset=utf-8",
        )
        schema = resp.json()
        assert isinstance(schema, dict)

    def test_openapi_version_field(self, client):
        """Schema must contain openapi version string."""
        schema = client.get("/openapi.json").json()
        assert "openapi" in schema
        assert schema["openapi"].startswith("3.")

    def test_openapi_info_section(self, client):
        """Info must contain title, description, version, and contact."""
        schema = client.get("/openapi.json").json()
        info = schema.get("info", {})
        assert info.get("title") == "OpenAgents API"
        assert info.get("version") == "0.1.0"
        assert "description" in info
        assert "contact" in info


# ── Security Scheme Tests ───────────────────────────────────────────────────


class TestSecuritySchemes:
    """Verify security schemes are registered correctly."""

    def test_security_schemes_section_exists(self, client):
        """Schema must have a components.securitySchemes section."""
        schema = client.get("/openapi.json").json()
        schemes = schema.get("components", {}).get("securitySchemes", {})
        assert len(schemes) > 0

    def test_bearer_auth_scheme(self, client):
        """bearerAuth scheme must be defined as http bearer."""
        schema = client.get("/openapi.json").json()
        bearer = schema["components"]["securitySchemes"].get("bearerAuth", {})
        assert bearer.get("type") == "http"
        assert bearer.get("scheme") == "bearer"
        assert bearer.get("bearerFormat") == "JWT"

    def test_api_key_auth_scheme(self, client):
        """apiKeyAuth scheme must be defined as apiKey in header."""
        schema = client.get("/openapi.json").json()
        apikey = schema["components"]["securitySchemes"].get("apiKeyAuth", {})
        assert apikey.get("type") == "apiKey"
        assert apikey.get("in") == "header"
        assert apikey.get("name") == "X-API-Key"

    def test_security_schemes_have_descriptions(self, client):
        """All security schemes must have a description."""
        schema = client.get("/openapi.json").json()
        for name, scheme in schema["components"]["securitySchemes"].items():
            assert "description" in scheme, f"Scheme '{name}' missing description"


# ── Tag Tests ───────────────────────────────────────────────────────────────


class TestTags:
    """Verify tag metadata is present."""

    def test_tags_section_exists(self, client):
        """Schema must have a tags array."""
        schema = client.get("/openapi.json").json()
        assert "tags" in schema
        assert len(schema["tags"]) > 0

    def test_required_tags_present(self, client):
        """Must have agents, tasks, payments, leaderboard, health tags."""
        schema = client.get("/openapi.json").json()
        tag_names = {t["name"] for t in schema["tags"]}
        for required in ("agents", "tasks", "payments", "leaderboard", "health"):
            assert required in tag_names, f"Missing tag: {required}"

    def test_tags_have_descriptions(self, client):
        """All tags must have a description."""
        schema = client.get("/openapi.json").json()
        for tag in schema["tags"]:
            assert "description" in tag, f"Tag '{tag.get('name')}' missing description"


# ── Error Schema Tests ──────────────────────────────────────────────────────


class TestErrorSchemas:
    """Verify error response schema components exist."""

    def test_error_response_schema_exists(self, client):
        """Components.schemas must include ErrorResponse."""
        schema = client.get("/openapi.json").json()
        schemas = schema.get("components", {}).get("schemas", {})
        assert "ErrorResponse" in schemas

    def test_error_response_required_fields(self, client):
        """ErrorResponse must have code, message, and status_code as required."""
        schema = client.get("/openapi.json").json()
        err_schema = schema["components"]["schemas"]["ErrorResponse"]
        required = set(err_schema.get("required", []))
        for field in ("code", "message", "status_code"):
            assert field in required, f"ErrorResponse missing required field: {field}"


# ── Route Documentation Tests ───────────────────────────────────────────────


class TestRouteDocumentation:
    """Verify endpoints have proper OpenAPI documentation."""

    def test_routes_have_summary(self, client):
        """Every endpoint must have a summary."""
        schema = client.get("/openapi.json").json()
        paths = schema.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                assert "summary" in details, f"{method.upper()} {path} missing summary"
                assert "description" in details, f"{method.upper()} {path} missing description"

    def test_health_endpoint_documented(self, client):
        """Health endpoint must be tagged and have summary."""
        schema = client.get("/openapi.json").json()
        health = schema["paths"].get("/health", {}).get("get", {})
        assert health.get("summary") == "API health check"
        assert "health" in health.get("tags", [])

    def test_leaderboard_endpoint_documented(self, client):
        """Leaderboard endpoint must be tagged and have summary."""
        schema = client.get("/openapi.json").json()
        lb = schema["paths"].get("/leaderboard", {}).get("get", {})
        assert lb.get("summary") == "Get agent leaderboard"
        assert "leaderboard" in lb.get("tags", [])

    def test_agent_list_endpoint_has_parameters(self, client):
        """Agent list endpoint must document query parameters."""
        schema = client.get("/openapi.json").json()
        params = schema["paths"].get("/agents", {}).get("get", {}).get("parameters", [])
        param_names = {p["name"] for p in params}
        for expected in ("active_only", "min_reputation", "limit", "offset"):
            assert expected in param_names, f"Missing parameter: {expected}"


# ── Server Config Tests ─────────────────────────────────────────────────────


class TestServerConfig:
    """Verify server configuration is present."""

    def test_servers_section_exists(self, client):
        """Schema must have a servers array."""
        schema = client.get("/openapi.json").json()
        assert "servers" in schema
        assert len(schema["servers"]) > 0


# ── Schema Integrity Tests ──────────────────────────────────────────────────


class TestSchemaIntegrity:
    """Verify overall schema integrity."""

    def test_paths_section_exists(self, client):
        """Schema must have a paths section."""
        schema = client.get("/openapi.json").json()
        assert "paths" in schema
        assert len(schema["paths"]) > 0
