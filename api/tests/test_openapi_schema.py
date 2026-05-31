from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)

PROTECTED_ROUTES = [
    "/agents",
    "/agents/{agent_id}",
    "/tasks",
    "/tasks/{task_id}",
    "/leaderboard",
]

EXPECTED_SECURITY = [{"BearerAuth": []}, {"ApiKeyAuth": []}]
EXPECTED_ERROR_CODES = {"400", "401", "403", "404", "429"}


def test_openapi_includes_security_schemes():
    schema = client.get("/openapi.json").json()
    security_schemes = schema["components"]["securitySchemes"]

    assert "BearerAuth" in security_schemes
    assert "ApiKeyAuth" in security_schemes
    assert security_schemes["BearerAuth"]["type"] == "http"
    assert security_schemes["ApiKeyAuth"]["type"] == "apiKey"


def test_protected_routes_have_security_and_error_responses():
    schema = client.get("/openapi.json").json()

    for route in PROTECTED_ROUTES:
        operation = schema["paths"][route]["get"]
        assert operation["security"] == EXPECTED_SECURITY
        assert EXPECTED_ERROR_CODES.issubset(operation["responses"].keys())
        for code in EXPECTED_ERROR_CODES:
            response_schema = operation["responses"][code]["content"]["application/json"]["schema"]
            assert response_schema["$ref"].endswith("/ErrorResponse")


def test_openapi_models_include_examples():
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]

    for model_name in [
        "AgentResponse",
        "TaskResponse",
        "LeaderboardEntry",
        "ErrorResponse",
        "HealthResponse",
    ]:
        assert "example" in components[model_name]

