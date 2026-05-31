from api.main import app


PROTECTED_PATHS = [
    "/agents",
    "/agents/{agent_id}",
    "/tasks",
    "/tasks/{task_id}",
    "/leaderboard",
]


def test_openapi_schema_contains_required_top_level_sections():
    schema = app.openapi()
    assert schema["openapi"].startswith("3.")
    assert "paths" in schema
    assert "components" in schema
    assert "schemas" in schema["components"]


def test_openapi_security_schemes_and_operation_security_are_documented():
    schema = app.openapi()
    security_schemes = schema["components"]["securitySchemes"]

    assert "BearerAuth" in security_schemes
    assert security_schemes["BearerAuth"]["type"] == "http"
    assert security_schemes["BearerAuth"]["scheme"] == "bearer"

    assert "ApiKeyAuth" in security_schemes
    assert security_schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert security_schemes["ApiKeyAuth"]["in"] == "header"
    assert security_schemes["ApiKeyAuth"]["name"] == "X-API-Key"

    for path in PROTECTED_PATHS:
        operation = schema["paths"][path]["get"]
        assert {"BearerAuth": []} in operation["security"]
        assert {"ApiKeyAuth": []} in operation["security"]


def test_openapi_documents_standard_error_responses_and_examples():
    schema = app.openapi()
    operation = schema["paths"]["/agents/{agent_id}"]["get"]

    for status_code in ("400", "401", "403", "404", "429"):
        assert status_code in operation["responses"]
        payload = (
            operation["responses"][status_code]["content"]["application/json"]["example"]
        )
        assert "error" in payload
        assert "message" in payload
        assert "code" in payload

    components = schema["components"]["schemas"]
    for model_name in [
        "AgentResponse",
        "TaskResponse",
        "LeaderboardEntry",
        "HealthResponse",
        "ErrorResponse",
    ]:
        assert "example" in components[model_name]
