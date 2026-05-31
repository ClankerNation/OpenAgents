from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_openapi_contains_both_security_schemes() -> None:
    schema = client.get("/openapi.json").json()
    security_schemes = schema["components"]["securitySchemes"]

    assert "JWTBearer" in security_schemes
    assert security_schemes["JWTBearer"]["type"] == "http"
    assert security_schemes["JWTBearer"]["scheme"] == "bearer"

    assert "ApiKeyAuth" in security_schemes
    assert security_schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert security_schemes["ApiKeyAuth"]["in"] == "header"
    assert security_schemes["ApiKeyAuth"]["name"] == "X-API-Key"


def test_protected_endpoints_have_security_requirements() -> None:
    schema = client.get("/openapi.json").json()
    protected_operations = [
        ("/agents", "get"),
        ("/agents/{agent_id}", "get"),
        ("/tasks", "get"),
        ("/tasks/{task_id}", "get"),
        ("/leaderboard", "get"),
    ]

    for path, method in protected_operations:
        operation = schema["paths"][path][method]
        security = operation.get("security", [])
        security_keys = {next(iter(requirement.keys())) for requirement in security}
        assert "JWTBearer" in security_keys
        assert "ApiKeyAuth" in security_keys

    assert "security" not in schema["paths"]["/health"]["get"]


def test_openapi_error_responses_and_model_examples() -> None:
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/agents"]["get"]["responses"]

    for status_code in ("400", "401", "403", "404", "429"):
        assert status_code in responses
        response_schema = responses[status_code]["content"]["application/json"]["schema"]
        assert response_schema["$ref"] == "#/components/schemas/ErrorResponse"

    component_schemas = schema["components"]["schemas"]
    for model_name in (
        "AgentResponse",
        "TaskResponse",
        "LeaderboardEntry",
        "HealthResponse",
        "ErrorResponse",
    ):
        assert "example" in component_schemas[model_name]
