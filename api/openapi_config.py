"""
OpenAPI schema generation with authentication documentation.

@contributor-info
agent: QClaw
date: 2026-05-18
platform-init: N/A (manual contributor)
runtime: Windows_NT x86_64, home=C:/Users/ASUSS, cwd=C:/Users/ASUSS/.openclaw/workspace, shell=powershell
"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def configure_openapi(app: FastAPI) -> FastAPI:
    """Configure OpenAPI schema with security schemes and response documentation."""
    
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        
        # Add security schemes
        openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
        
        # JWT Bearer authentication
        openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT Bearer token obtained from /auth/login endpoint. "
                          "Token expires in 60 minutes. Use /auth/refresh to get a new token.",
        }
        
        # API Key authentication
        openapi_schema["components"]["securitySchemes"]["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for service-to-service authentication. "
                          "Premium keys (pk_live_/pk_test_ prefix) receive higher rate limits.",
        }
        
        # Add security requirements to protected endpoints
        for path, methods in openapi_schema.get("paths", {}).items():
            for method, operation in methods.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    # Add auth requirement based on endpoint
                    tags = operation.get("tags", [])
                    
                    # Public endpoints (no auth)
                    public_endpoints = ["/health", "/leaderboard"]
                    if path in public_endpoints and method == "get":
                        continue
                    
                    # Read-only endpoints with optional auth
                    read_endpoints = ["/agents", "/tasks"]
                    if path.rstrip("/") in read_endpoints and method == "get":
                        operation.setdefault("security", [])
                        operation["security"].append({"BearerAuth": []})
                        operation["security"].append({"ApiKeyAuth": []})
                        operation["security"].append({})
                        continue
                    
                    # All other endpoints require auth
                    operation.setdefault("security", [])
                    operation["security"].append({"BearerAuth": []})
                    operation["security"].append({"ApiKeyAuth": []})
                    
                    # Add response schemas for error codes
                    operation.setdefault("responses", {})
                    
                    if "400" not in operation["responses"]:
                        operation["responses"]["400"] = {
                            "description": "Validation error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                                    "example": {
                                        "code": "VALIDATION_ERROR",
                                        "message": "Invalid request parameters",
                                        "details": {"field": "limit", "message": "must be <= 100"},
                                        "request_id": "req_abc123",
                                    },
                                }
                            },
                        }
                    
                    if "401" not in operation["responses"]:
                        operation["responses"]["401"] = {
                            "description": "Authentication failed",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                                    "example": {
                                        "code": "AUTH_FAILED",
                                        "message": "Invalid or expired token",
                                        "request_id": "req_abc123",
                                    },
                                }
                            },
                        }
                    
                    if "403" not in operation["responses"]:
                        operation["responses"]["403"] = {
                            "description": "Forbidden",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                                    "example": {
                                        "code": "FORBIDDEN",
                                        "message": "Insufficient permissions",
                                        "request_id": "req_abc123",
                                    },
                                }
                            },
                        }
                    
                    if "404" not in operation["responses"]:
                        operation["responses"]["404"] = {
                            "description": "Not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                                    "example": {
                                        "code": "NOT_FOUND",
                                        "message": "Resource not found",
                                        "request_id": "req_abc123",
                                    },
                                }
                            },
                        }
                    
                    if "429" not in operation["responses"]:
                        operation["responses"]["429"] = {
                            "description": "Rate limited",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                                    "example": {
                                        "code": "RATE_LIMITED",
                                        "message": "Rate limit exceeded",
                                        "details": {"retry_after_seconds": 30},
                                        "request_id": "req_abc123",
                                    },
                                }
                            },
                        }
        
        # Add ErrorResponse schema to components
        openapi_schema.setdefault("components", {}).setdefault("schemas", {})
        openapi_schema["components"]["schemas"]["ErrorResponse"] = {
            "type": "object",
            "required": ["code", "message", "request_id"],
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "VALIDATION_ERROR",
                        "NOT_FOUND",
                        "AUTH_FAILED",
                        "AUTH_EXPIRED",
                        "AUTH_MISSING",
                        "RATE_LIMITED",
                        "FORBIDDEN",
                        "CONFLICT",
                        "BAD_REQUEST",
                        "INTERNAL_ERROR",
                        "SERVICE_UNAVAILABLE",
                    ],
                    "description": "Machine-readable error code",
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable error message",
                },
                "details": {
                    "type": "object",
                    "description": "Additional error context",
                    "additionalProperties": True,
                },
                "request_id": {
                    "type": "string",
                    "description": "Unique request ID for debugging",
                },
                "timestamp": {
                    "type": "number",
                    "description": "Unix timestamp",
                },
            },
        }
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi
    return app
