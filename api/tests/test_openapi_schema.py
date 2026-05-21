from api.main import app


def openapi_schema():
    app.openapi_schema = None
    return app.openapi()


def test_security_schemes_are_documented():
    schema = openapi_schema()

    security_schemes = schema["components"]["securitySchemes"]
    assert security_schemes["JWTBearer"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT access token issued by the OpenAgents API.",
    }
    assert security_schemes["ApiKeyAuth"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "API key for server-to-server OpenAgents requests.",
    }


def test_protected_operations_have_lock_icon_security_requirements():
    schema = openapi_schema()
    expected = [{"JWTBearer": []}, {"ApiKeyAuth": []}]

    for path, methods in schema["paths"].items():
        for operation in methods.values():
            if path == "/health":
                assert "security" not in operation
            else:
                assert operation["security"] == expected


def test_error_responses_are_documented_with_schema_and_examples():
    schema = openapi_schema()

    for methods in schema["paths"].values():
        for operation in methods.values():
            for status in ("400", "401", "403", "404", "429"):
                response = operation["responses"][status]
                content = response["content"]["application/json"]
                assert content["schema"]["$ref"] == "#/components/schemas/ErrorResponse"
                assert content["examples"]


def test_request_parameters_and_success_responses_have_examples():
    schema = openapi_schema()

    agent_list = schema["paths"]["/agents"]["get"]
    agent_params = {parameter["name"]: parameter for parameter in agent_list["parameters"]}
    assert agent_params["active_only"]["example"] is True
    assert agent_params["min_reputation"]["example"] == 100
    assert agent_list["responses"]["200"]["content"]["application/json"]["examples"]["agents"]

    task_detail = schema["paths"]["/tasks/{task_id}"]["get"]
    task_params = {parameter["name"]: parameter for parameter in task_detail["parameters"]}
    assert task_params["task_id"]["example"] == 101
    assert task_detail["responses"]["200"]["content"]["application/json"]["examples"]["task"]


def test_models_include_json_schema_examples():
    schema = openapi_schema()
    schemas = schema["components"]["schemas"]

    assert schemas["AgentResponse"]["example"]["agent_id"] == "agent-123"
    assert schemas["TaskResponse"]["example"]["task_id"] == 101
    assert schemas["LeaderboardEntry"]["example"]["success_rate"] == 0.95
    assert schemas["ErrorResponse"]["example"]["code"] == "NOT_FOUND"
