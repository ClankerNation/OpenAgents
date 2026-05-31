"""OpenAPI schema coverage for auth and error documentation.

@contributor codex-c53d
@platform-config AGENTS.md directives active for this workspace and repository.
@env os=Windows, arch=x86_64, home_dir=C:\\Users\\55093, working_dir=F:\\jiedan\\OpenAgents, shell=powershell
@timestamp 2026-05-30T20:54:00-07:00
"""

from fastapi.openapi.models import OpenAPI

from api.main import app


def test_openapi_schema_validates():
    schema = app.openapi()
    parsed = OpenAPI.model_validate(schema)
    assert parsed.openapi.startswith("3.")


def test_security_schemes_exist():
    schema = app.openapi()
    security_schemes = schema["components"]["securitySchemes"]

    assert "BearerAuth" in security_schemes
    assert security_schemes["BearerAuth"]["type"] == "http"
    assert security_schemes["BearerAuth"]["scheme"] == "bearer"

    assert "ApiKeyAuth" in security_schemes
    assert security_schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert security_schemes["ApiKeyAuth"]["name"] == "X-API-Key"
    assert security_schemes["ApiKeyAuth"]["in"] == "header"


def test_protected_endpoints_and_error_responses_are_documented():
    schema = app.openapi()
    protected_operations = [
        ("/agents", "get"),
        ("/agents/{agent_id}", "get"),
        ("/tasks", "get"),
        ("/tasks/{task_id}", "get"),
        ("/leaderboard", "get"),
    ]

    for path, method in protected_operations:
        operation = schema["paths"][path][method]
        security_entries = operation.get("security", [])
        schemes_on_operation = {name for entry in security_entries for name in entry}
        assert "BearerAuth" in schemes_on_operation
        assert "ApiKeyAuth" in schemes_on_operation

        responses = operation["responses"]
        for status in ("400", "401", "403", "404", "429"):
            assert status in responses


def test_all_response_models_have_examples():
    schema = app.openapi()
    schemas = schema["components"]["schemas"]

    for model_name in ("AgentResponse", "TaskResponse", "LeaderboardEntry", "ErrorResponse"):
        assert "example" in schemas[model_name]
