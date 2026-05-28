"""Tests for OpenAPI schema documentation."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


@pytest.fixture
def schema():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


class TestSecuritySchemes:
    def test_bearer_auth_scheme_exists(self, schema):
        schemes = schema["components"]["securitySchemes"]
        assert "BearerAuth" in schemes
        bearer = schemes["BearerAuth"]
        assert bearer["type"] == "http"
        assert bearer["scheme"] == "bearer"
        assert bearer["bearerFormat"] == "JWT"

    def test_api_key_auth_scheme_exists(self, schema):
        schemes = schema["components"]["securitySchemes"]
        assert "ApiKeyAuth" in schemes
        api_key = schemes["ApiKeyAuth"]
        assert api_key["type"] == "apiKey"
        assert api_key["in"] == "header"
        assert api_key["name"] == "X-API-Key"

    def test_global_security_defined(self, schema):
        assert "security" in schema
        security = schema["security"]
        assert any("BearerAuth" in s for s in security)
        assert any("ApiKeyAuth" in s for s in security)


class TestErrorResponses:
    def test_error_response_schema_exists(self, schema):
        schemas = schema["components"]["schemas"]
        assert "ErrorResponse" in schemas
        error_schema = schemas["ErrorResponse"]
        assert "detail" in error_schema["properties"]

    def test_endpoints_have_error_responses(self, schema):
        paths = schema["paths"]
        for path, methods in paths.items():
            for method, details in methods.items():
                if method in ("get", "post", "put", "delete", "patch"):
                    responses = details.get("responses", {})
                    assert "401" in responses or "404" in responses, (
                        f"{method.upper()} {path} missing error responses"
                    )


class TestModelExamples:
    def test_agent_response_has_example(self, schema):
        schemas = schema["components"]["schemas"]
        if "AgentResponse" in schemas:
            agent = schemas["AgentResponse"]
            assert "example" in agent or "examples" in agent

    def test_task_response_has_example(self, schema):
        schemas = schema["components"]["schemas"]
        if "TaskResponse" in schemas:
            task = schemas["TaskResponse"]
            assert "example" in task or "examples" in task


class TestEndpointDocumentation:
    def test_main_endpoints_have_summary(self, schema):
        main_paths = ["/agents", "/tasks", "/leaderboard", "/health"]
        for path in main_paths:
            if path in schema["paths"]:
                for method, details in schema["paths"][path].items():
                    if method in ("get", "post", "put", "delete", "patch"):
                        assert "summary" in details, (
                            f"{method.upper()} {path} missing summary"
                        )

    def test_openapi_spec_is_valid(self, schema):
        assert "openapi" in schema
        assert "paths" in schema
        assert "components" in schema


class TestDocsEndpoints:
    def test_swagger_ui_available(self):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_available(self):
        response = client.get("/redoc")
        assert response.status_code == 200
