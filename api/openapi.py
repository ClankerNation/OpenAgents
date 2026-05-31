from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI

def generate_openapi_schema(app: FastAPI) -> dict:
    schema = get_openapi(
        title="OpenAgents API",
        version="2.0.0",
        description="Autonomous agents orchestration API",
        routes=app.routes,
    )
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    schema["security"] = [{"BearerAuth": []}]
    return schema

def setup_docs(app: FastAPI):
    @app.get("/openapi.json")
    async def get_openapi_json():
        return generate_openapi_schema(app)