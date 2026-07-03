import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.main import app

client = TestClient(app)


def test_openapi_security_schemes_present():
    schema = app.openapi()
    security_schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "HTTPBearer" in security_schemes
    assert security_schemes["HTTPBearer"]["type"] == "http"
    assert security_schemes["HTTPBearer"]["scheme"] == "bearer"
    assert "APIKeyHeader" in security_schemes
    assert security_schemes["APIKeyHeader"]["type"] == "apiKey"
    assert security_schemes["APIKeyHeader"]["name"] == "X-API-Key"


def test_protected_endpoint_requires_auth():
    response = client.get("/auth/demo")
    assert response.status_code == 401


def test_openapi_has_error_responses():
    schema = app.openapi()
    health = schema["paths"]["/health"]["get"]
    assert "200" in health["responses"]
    agents = schema["paths"]["/agents/{agent_id}"]["get"]
    assert "404" in agents["responses"]
    assert "429" in agents["responses"]


def test_openapi_has_examples():
    schema = app.openapi()
    agent_schema = schema["components"]["schemas"]["AgentResponse"]
    assert "example" in agent_schema


def test_openapi_tags_present():
    schema = app.openapi()
    assert len(schema.get("tags", [])) > 0
    tag_names = [t["name"] for t in schema["tags"]]
    assert "agents" in tag_names
    assert "tasks" in tag_names
    assert "health" in tag_names
