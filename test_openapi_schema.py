"""Tests for OpenAPI schema generation with authentication documentation.

Verifies:
- Security schemes are registered (JWT Bearer + API Key)
- Error response schemas are documented
- Endpoints have proper response models
- Example values provided for models
"""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_openapi_schema_has_security_schemes():
    """Verify both auth methods are visible in the OpenAPI spec."""
    schema = client.get("/openapi.json").json()
    components = schema.get("components", {})
    security_schemes = components.get("securitySchemes", {})

    assert "JWT Bearer" in security_schemes, (
        "Missing JWT Bearer security scheme"
    )
    assert "API Key" in security_schemes, (
        "Missing API Key security scheme"
    )

    jwt_scheme = security_schemes["JWT Bearer"]
    assert jwt_scheme["type"] == "http"
    assert jwt_scheme["scheme"] == "bearer"
    assert jwt_scheme["bearerFormat"] == "JWT"

    api_key_scheme = security_schemes["API Key"]
    assert api_key_scheme["type"] == "apiKey"
    assert api_key_scheme["in"] == "header"
    assert api_key_scheme["name"] == "X-API-Key"


def test_openapi_schema_has_paths():
    """Verify all expected paths are documented."""
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})

    expected_paths = [
        "/agents",
        "/agents/{agent_id}",
        "/tasks",
        "/tasks/{task_id}",
        "/leaderboard",
        "/health",
    ]
    for path in expected_paths:
        assert path in paths, f"Missing path {path} in OpenAPI schema"


def test_endpoints_have_tags():
    """Verify each endpoint is tagged."""
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})

    for path, methods in paths.items():
        for method, detail in methods.items():
            tags = detail.get("tags", [])
            assert len(tags) > 0, (
                f"Endpoint {method.upper()} {path} has no tags"
            )


def test_endpoints_have_summary():
    """Verify each endpoint has a summary."""
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})

    for path, methods in paths.items():
        for method, detail in methods.items():
            assert "summary" in detail, (
                f"Endpoint {method.upper()} {path} lacks summary"
            )
            assert len(detail["summary"]) > 0, (
                f"Endpoint {method.upper()} {path} has empty summary"
            )


def test_error_schemas_defined():
    """Verify error response models are defined."""
    schema = client.get("/openapi.json").json()
    components = schema.get("components", {})
    schemas = components.get("schemas", {})

    error_schema = schemas.get("ErrorResponse")
    assert error_schema is not None, "Missing ErrorResponse schema"
    props = error_schema.get("properties", {})
    assert "error" in props, "ErrorResponse missing 'error' field"
    assert "detail" in props, "ErrorResponse missing 'detail' field"


def test_response_models_have_examples():
    """Verify response models include example values."""
    schema = client.get("/openapi.json").json()
    schemas = schema.get("components", {}).get("schemas", {})

    models_with_examples = ["AgentResponse", "TaskResponse", "LeaderboardEntry"]
    for model_name in models_with_examples:
        model = schemas.get(model_name)
        assert model is not None, f"Missing schema for {model_name}"
        assert "example" in model or "examples" in model, (
            f"{model_name} has no example values"
        )


def test_agent_endpoints_return_correct_response():
    """Verify actual endpoint responses match documented schemas."""
    response = client.get("/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    response = client.get("/agents/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data

    response = client.get("/tasks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_leaderboard_endpoint():
    """Verify leaderboard endpoint returns expected shape."""
    response = client.get("/leaderboard")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_security_on_mutating_endpoints():
    """Verify POST/PUT/PATCH/DELETE endpoints have security requirements."""
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    for path, methods in paths.items():
        for method, detail in methods.items():
            if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
                assert "security" in detail, (
                    f"{method.upper()} {path} has no security requirements"
                )
