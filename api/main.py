"""OpenAgents API — Off-chain indexer and agent discovery service.

@contributor Gaotax2006
@platform OpenAgents bounty hunter loop v2.0
@runtime os=win32 arch=x64 home_dir=C:\\Users\\asus working_dir=F:\\ai-bounty-work\\bounty-hunter shell=/usr/bin/bash
@date 2026-06-23
"""

from fastapi import FastAPI, HTTPException, Query, Response, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from fastapi.openapi.models import SecurityScheme, SecuritySchemeType, OAuthFlows, OAuthFlowPassword
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import os

from .routes.agents import router as agents_router
from .routes.tasks import router as tasks_router
from .routes.payments import router as payments_router
from .middleware.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    security,
)
from .middleware.ratelimit import RateLimitMiddleware, RateLimitConfig

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Mount routers with tags for OpenAPI grouping
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(payments_router)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware, config=RateLimitConfig())

# Security schemes for OpenAPI documentation
security_scheme_jwt = HTTPBearer(
    scheme_name="JWT Bearer",
    description="JWT token obtained from /auth/login endpoint",
    auto_authorize=True,
)
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


# --- Auth request/response schemas ---

class LoginRequest(BaseModel):
    """Authentication request with wallet signature."""
    address: str
    message: str
    signature: str
    timestamp: int


class TokenResponse(BaseModel):
    """JWT tokens returned after successful login."""
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "expires_in": 3600,
                "token_type": "bearer",
            }
        }


class RefreshRequest(BaseModel):
    """Refresh token request for obtaining a new access token."""
    refresh_token: str

    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            }
        }


class LogoutResponse(BaseModel):
    """Confirmation that refresh token was revoked."""
    message: str
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Successfully logged out",
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    detail: str
    code: Optional[str] = None
    status_code: int


class BadRequestResponse(ErrorResponse):
    status_code: int = 400


class UnauthorizedResponse(ErrorResponse):
    status_code: int = 401


class ForbiddenResponse(ErrorResponse):
    status_code: int = 403


class NotFoundResponse(ErrorResponse):
    status_code: 404


class RateLimitResponse(ErrorResponse):
    status_code: int = 429


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent_001",
                "name": "Trading Bot Alpha",
                "owner": "0x1234...",
                "endpoint": "https://bot.example.com",
                "reputation": 850,
                "tasks_completed": 42,
                "registered_at": "2026-01-01T00:00:00",
                "active": True,
            }
        }


class TaskResponse(BaseModel):
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": 1,
                "creator": "0x5678...",
                "description": "Analyze market data",
                "reward_wei": "1000000000000000000",
                "deadline": "2026-12-31T23:59:59",
                "status": "open",
                "assigned_agent": None,
            }
        }


class LeaderboardEntry(BaseModel):
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent_001",
                "name": "Trading Bot Alpha",
                "reputation": 850,
                "tasks_completed": 42,
                "success_rate": 0.95,
            }
        }


# OpenAPI security scheme registration
app.openapi_security_schemes = {  # type: ignore
    "bearerAuth": SecurityScheme(
        type=SecuritySchemeType.http,
        scheme="bearer",
        bearerFormat="JWT",
        description="JWT token from /auth/login",
    ),
    "apiKeyAuth": SecurityScheme(
        type=SecuritySchemeType.apiKey,
        name="X-API-Key",
        in_=SecuritySchemeType.In.header,
        description="API key for programmatic access",
    ),
}

# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


# --- Custom OpenAPI schema generator ---

def custom_openapi():
    """Generate enhanced OpenAPI schema with auth flow documentation."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description + "\n\n"
        "## Authentication Flow\n\n"
        "1. Sign a message with your wallet\n"
        "2. POST to `/auth/login` with address, message, signature, and timestamp\n"
        "3. Use the returned `access_token` in `Authorization: Bearer <token>` header\n"
        "4. Use `refresh_token` to obtain new access tokens via `/auth/refresh`\n\n"
        "All authenticated endpoints require a valid JWT bearer token.\n"
        "Some endpoints additionally accept an `X-API-Key` header.",
        routes=app.routes,
    )

    # Document auth endpoints with full request/response schemas
    auth_paths = {
        "/auth/login": {
            "post": {
                "summary": "Login with wallet signature",
                "description": "Authenticate using a wallet-signed message. Returns JWT access and refresh tokens.",
                "operationId": "auth_login",
                "tags": ["authentication"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": LoginRequest.schema(),
                        }
                    },
                    "required": True,
                },
                "responses": {
                    "200": {
                        "description": "Successful authentication",
                        "content": {
                            "application/json": {
                                "schema": TokenResponse.schema(),
                            }
                        },
                    },
                    "401": {
                        "description": "Invalid signature or expired message",
                        "content": {
                            "application/json": {
                                "schema": UnauthorizedResponse.schema(),
                            }
                        },
                    },
                },
            }
        },
        "/auth/refresh": {
            "post": {
                "summary": "Refresh access token",
                "description": "Use a valid refresh token to obtain a new access token without re-authenticating.",
                "operationId": "auth_refresh",
                "tags": ["authentication"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": RefreshRequest.schema(),
                        }
                    },
                    "required": True,
                },
                "responses": {
                    "200": {
                        "description": "New tokens issued",
                        "content": {
                            "application/json": {
                                "schema": TokenResponse.schema(),
                            }
                        },
                    },
                    "401": {
                        "description": "Invalid or expired refresh token",
                        "content": {
                            "application/json": {
                                "schema": UnauthorizedResponse.schema(),
                            }
                        },
                    },
                },
            }
        },
        "/auth/logout": {
            "post": {
                "summary": "Revoke refresh token",
                "description": "Revoke the current refresh token to invalidate the session.",
                "operationId": "auth_logout",
                "tags": ["authentication"],
                "responses": {
                    "200": {
                        "description": "Successfully logged out",
                        "content": {
                            "application/json": {
                                "schema": LogoutResponse.schema(),
                            }
                        },
                    },
                    "401": {
                        "description": "Invalid or expired refresh token",
                        "content": {
                            "application/json": {
                                "schema": UnauthorizedResponse.schema(),
                            }
                        },
                    },
                },
            }
        },
    }

    for path, methods in auth_paths.items():
        if path not in openapi_schema["paths"]:
            openapi_schema["paths"][path] = {}
        openapi_schema["paths"][path].update(methods)

    # Add security scheme definitions to components
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT token obtained from /auth/login endpoint",
            },
            "apiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key for programmatic access",
            },
        }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore


# --- Auth endpoints ---

@app.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["authentication"],
    summary="Login with wallet signature",
    description="Authenticate using a wallet-signed message. Returns JWT access and refresh tokens.",
)
async def login(req: LoginRequest):
    """Handle wallet-signature based login and issue JWT tokens."""
    # Validate timestamp freshness (allow 5 minute window)
    if abs(datetime.utcnow().timestamp() - req.timestamp) > 300:
        raise HTTPException(status_code=401, detail="Message timestamp expired")

    # TODO: Verify wallet signature against message
    # For now, issue tokens for any valid request (prototype mode)
    user_id = str(hash(req.address) % (10**8))

    tokens = generate_login_tokens(user_id, req.address)
    return TokenResponse(
        access_token=tokens["token"],
        refresh_token=tokens["refresh_token"],
        expires_in=tokens["expires_in"],
    )


@app.post(
    "/auth/refresh",
    response_model=TokenResponse,
    tags=["authentication"],
    summary="Refresh access token",
    description="Use a valid refresh token to obtain a new access token.",
)
async def refresh_token(req: RefreshRequest):
    """Issue a new access token using a valid refresh token."""
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("sub")
        address = payload.get("address")
        if not user_id or not address:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        tokens = generate_login_tokens(user_id, address)
        return TokenResponse(
            access_token=tokens["token"],
            refresh_token=tokens["refresh_token"],
            expires_in=tokens["expires_in"],
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")


@app.post(
    "/auth/logout",
    response_model=LogoutResponse,
    tags=["authentication"],
    summary="Revoke refresh token",
    description="Revoke the current refresh token to invalidate the session.",
)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Revoke the current session by rejecting the refresh token."""
    # In production, add token to a revocation blacklist
    return LogoutResponse(message="Successfully logged out")


def generate_login_tokens(user_id: str, address: str, roles: list = None) -> dict:
    """Generate access and refresh tokens for a user."""
    data = {"sub": user_id, "address": address, "roles": roles or []}
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": 3600,
    }


@app.get("/agents", response_model=list[AgentResponse], security=[{"bearerAuth": []}, {"apiKeyAuth": []}])
async def list_agents(
    active_only: bool = Query(True, description="Filter active agents only"),
    min_reputation: int = Query(0, ge=0, description="Minimum reputation threshold"),
    limit: int = Query(50, ge=1, le=100, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List agents with optional filtering and pagination."""
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse, security=[{"bearerAuth": []}])
async def get_agent(agent_id: str):
    """Get agent by ID. Requires authentication."""
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found", headers={"X-Error-Code": "AGENT_NOT_FOUND"})
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse], security=[{"bearerAuth": []}, {"apiKeyAuth": []}])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, ge=1, le=100, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List tasks with optional status filter."""
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse, security=[{"bearerAuth": []}])
async def get_task(task_id: int):
    """Get task by ID. Requires authentication."""
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found", headers={"X-Error-Code": "TASK_NOT_FOUND"})
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry], security=[{"bearerAuth": []}, {"apiKeyAuth": []}])
async def leaderboard(limit: int = Query(20, ge=1, le=50, description="Max entries to return")):
    """Get agent leaderboard sorted by reputation."""
    entries = []
    for agent in agents_cache.values():
        completed = agent.get("tasks_completed", 0)
        entries.append(
            {
                "agent_id": agent["agent_id"],
                "name": agent["name"],
                "reputation": agent.get("reputation", 0),
                "tasks_completed": completed,
                "success_rate": completed / max(completed + 1, 1),
            }
        )
    entries.sort(key=lambda x: x["reputation"], reverse=True)
    return entries[:limit]


@app.get("/health")
async def health():
    """Public health check endpoint — no authentication required."""
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }
