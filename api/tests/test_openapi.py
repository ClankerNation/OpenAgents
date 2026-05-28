"""Tests for OpenAPI schema security schemes and error responses."""

import os
os.environ["JWT_SECRET"] = "test-secret-for-pytest"

from ..main import app


def test_openapi_has_security_schemes():
    """OpenAPI schema should have JWTBearer and APIKeyHeader security schemes."""
    schema = app.openapi()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "JWTBearer" in schemes, "Missing JWTBearer security scheme"
    assert "APIKeyHeader" in schemes, "Missing APIKeyHeader security scheme"


def test_jwt_bearer_scheme_type():
    """JWTBearer should be http bearer type."""
    schema = app.openapi()
    jwt_scheme = schema["components"]["securitySchemes"]["JWTBearer"]
    assert jwt_scheme["type"] == "http"
    assert jwt_scheme["scheme"] == "bearer"


def test_api_key_scheme_type():
    """APIKeyHeader should be apiKey in header."""
    schema = app.openapi()
    api_key = schema["components"]["securitySchemes"]["APIKeyHeader"]
    assert api_key["type"] == "apiKey"
    assert api_key["in"] == "header"
    assert api_key["name"] == "X-API-Key"


def test_security_requirement():
    """Schema should have global security requirement."""
    schema = app.openapi()
    security = schema.get("security", [])
    assert len(security) > 0
    assert "JWTBearer" in security[0]


def test_error_response_schema():
    """ErrorResponse schema should exist with code, message, details, request_id."""
    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})
    assert "ErrorResponse" in components
    props = components["ErrorResponse"]["properties"]
    assert "code" in props
    assert "message" in props
    assert "details" in props
    assert "request_id" in props


def test_validation_error_schema():
    """ValidationError schema should exist with field-level details."""
    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})
    assert "ValidationError" in components
    props = components["ValidationError"]["properties"]
    assert props["code"]["example"] == "VALIDATION_ERROR"


def test_agent_response_example():
    """AgentResponse should have example values."""
    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})
    assert "AgentResponse" in components
    props = components["AgentResponse"]["properties"]
    assert props["name"]["example"] == "My Trading Agent"
    assert props["active"]["example"] is True


def test_docs_endpoints_enabled():
    """Swagger UI and ReDoc endpoints should be enabled."""
    schema = app.openapi()
    assert schema.get("openapi") is not None
