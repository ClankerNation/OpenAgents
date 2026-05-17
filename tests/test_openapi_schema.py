"""
OpenAPI schema tests for the OpenAgents API.

Tests verify that:
- Swagger UI loads correctly
- Security schemes (JWT Bearer + API Key) are present in the OpenAPI spec
- Error response schemas are documented
- All endpoints have proper response documentation
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


class TestOpenAPISchema:
    """Verify the OpenAPI schema includes proper security and error documentation."""

    def test_openapi_json_returns_valid_schema(self):
        """GET /openapi.json returns a valid OpenAPI document."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["openapi"].startswith("3.")
        assert schema["info"]["title"] == "OpenAgents API"

    def test_security_schemes_present(self):
        """Security schemes for JWT Bearer and API Key are defined."""
        response = client.get("/openapi.json")
        schema = response.json()
        schemes = schema.get("components", {}).get("securitySchemes", {})
        assert "JWTBearer" in schemes, "JWT Bearer security scheme missing"
        assert "ApiKeyAuth" in schemes, "API Key security scheme missing"

        jwt_scheme = schemes["JWTBearer"]
        assert jwt_scheme["type"] == "http"
        assert jwt_scheme["scheme"] == "bearer"
        assert jwt_scheme["bearerFormat"] == "JWT"

        api_key_scheme = schemes["ApiKeyAuth"]
        assert api_key_scheme["type"] == "apiKey"
        assert api_key_scheme["in"] == "header"
        assert api_key_scheme["name"] == "X-API-Key"

    def test_global_security_applied(self):
        """Global security requirements reference both auth methods."""
        response = client.get("/openapi.json")
        schema = response.json()
        security = schema.get("security", [])
        assert len(security) >= 1, "No global security requirements defined"

        jwt_refs = [s for s in security if "JWTBearer" in s]
        assert len(jwt_refs) >= 1, "JWTBearer not in global security"

        api_key_refs = [s for s in security if "ApiKeyAuth" in s]
        assert len(api_key_refs) >= 1, "ApiKeyAuth not in global security"

    def test_error_response_schemas_documented(self):
        """Error response schemas are defined for standard HTTP error codes."""
        response = client.get("/openapi.json")
        schema = response.json()
        paths = schema.get("paths", {})

        # Check that endpoints have 404 documented
        agent_get = paths.get("/agents/{agent_id}", {}).get("get", {})
        responses = agent_get.get("responses", {})
        assert "404" in responses, "GET /agents/{agent_id} missing 404 response"

        # Check agents list has 422 for validation
        agents_list = paths.get("/agents", {}).get("get", {})
        responses = agents_list.get("responses", {})
        assert "422" in responses, "GET /agents missing 422 response"

    def test_docs_page_loads(self):
        """Swagger UI docs page loads."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()

    def test_redoc_page_loads(self):
        """ReDoc page loads."""
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "redoc" in response.text.lower()


class TestErrorResponseModels:
    """Verify error response models are properly structured."""

    def test_example_values_present(self):
        """Response models include example values."""
        response = client.get("/openapi.json")
        schema = response.json()
        components = schema.get("components", {}).get("schemas", {})

        # AgentResponse should have an example
        agent_schema = components.get("AgentResponse", {})
        assert "example" in agent_schema, "AgentResponse missing top-level example"

        # Error response should have examples
        auth_error = components.get("AuthErrorResponse", {})
        assert "example" in auth_error, "AuthErrorResponse missing example"


class TestRequestIDMiddleware:
    """Verify the request ID middleware is active."""

    def test_response_has_request_id(self):
        """Every response includes X-Request-ID header."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers, "Missing X-Request-ID header"

    def test_client_provided_request_id_preserved(self):
        """Client-provided X-Request-ID is preserved."""
        custom_id = "test-req-12345"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.headers.get("X-Request-ID") == custom_id, \
            f"Expected {custom_id}, got {response.headers.get('X-Request-ID')}"

    def test_error_response_includes_request_id(self):
        """Error responses include request_id in the body."""
        response = client.get("/agents/nonexistent")
        assert response.status_code == 404
        body = response.json()
        assert "request_id" in body, "Error response missing request_id field"


class TestExceptionHandler:
    """Verify the custom exception handler works."""

    def test_404_returns_not_found_code(self):
        response = client.get("/agents/nonexistent")
        assert response.status_code == 404
        body = response.json()
        assert body["error_code"] == "NOT_FOUND"

    def test_endpoints_accept_json(self):
        """Basic endpoint integration works."""
        response = client.get("/agents")
        assert response.status_code == 200

        response = client.get("/tasks")
        assert response.status_code == 200

        response = client.get("/leaderboard")
        assert response.status_code == 200
