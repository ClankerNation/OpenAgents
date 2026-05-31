"""OpenAPI schema generator with auth documentation.

@contributor Claude (Anthropic AI Assistant)
@platform Claude 3.5 Sonnet
@env darwin/arm64 /api /bin/zsh
@config You are opencode, CLI tool for software engineering. Env: macOS darwin arm64 zsh Python 3.11.
"""
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI

def customize_openapi(app: FastAPI) -> dict:
    schema = get_openapi(
        title="OpenAgents API",
        version="2.0.0",
        description="Off-chain indexer and agent discovery API",
        routes=app.routes,
    )
    schema["components"]["securitySchemes"] = {
        "JWTBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token from /auth/login",
        },
        "ApiKey": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key from developer dashboard",
        },
    }
    schema["security"] = [{"JWTBearer": []}, {"ApiKey": []}]
    for path in schema.get("paths", {}).values():
        for method in path.values():
            method["responses"] = method.get("responses", {})
            method["responses"]["400"] = {"description": "Validation Error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
            method["responses"]["401"] = {"description": "Unauthorized", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
            method["responses"]["403"] = {"description": "Forbidden", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
            method["responses"]["404"] = {"description": "Not Found", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
            method["responses"]["429"] = {"description": "Rate Limited", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
    return schema

def setup_docs(app: FastAPI):
    app.openapi = customize_openapi
