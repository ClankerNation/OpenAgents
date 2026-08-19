"""Tests for OpenAPI Security Documentation (Issue #185)."""
# @contributor-info ARO-Agentic
# @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
# @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

def test_openapi_schema_has_security_schemes():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    
    assert "components" in schema
    assert "securitySchemes" in schema["components"]
    
    schemes = schema["components"]["securitySchemes"]
    assert "jwtBearer" in schemes or "HTTPBearer" in str(schemes)
    assert "apiKey" in schemes or "APIKeyHeader" in str(schemes)

def test_openapi_schema_has_error_responses():
    response = client.get("/openapi.json")
    schema = response.json()
    
    paths = schema.get("paths", {})
    agents_get = paths.get("/agents/", {}).get("get", {})
    if not agents_get:
        agents_get = paths.get("/agents", {}).get("get", {})
        
    responses_in_path = agents_get.get("responses", {})
    
    # FastAPI injects global app responses directly into each path
    response_keys = [int(k) if str(k).isdigit() else k for k in responses_in_path.keys()]
    
    assert 400 in response_keys or "400" in responses_in_path
    assert 401 in response_keys or "401" in responses_in_path
    assert 403 in response_keys or "403" in responses_in_path
    assert 404 in response_keys or "404" in responses_in_path
    assert 429 in response_keys or "429" in responses_in_path

def test_openapi_endpoints_have_security_requirements():
    response = client.get("/openapi.json")
    schema = response.json()
    paths = schema.get("paths", {})
    
    agents_get = paths.get("/agents/", {}).get("get", {})
    if not agents_get:
        agents_get = paths.get("/agents", {}).get("get", {})
        
    assert "security" in agents_get
    security = agents_get["security"]
    assert isinstance(security, list)
    assert len(security) > 0
