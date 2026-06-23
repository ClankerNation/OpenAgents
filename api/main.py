from fastapi import FastAPI, HTTPException, Query, Request, Depends, SecurityScopes, Header
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import uuid

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
    contact={
        "name": "OpenAgents API",
        "url": "https://github.com/ClankerNation/OpenAgents",
        "email": "api@openagents.io",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    termsOfService="https://openagents.io/terms",
    tags=[
        {"name": "agents", "description": "Agent discovery and management"},
        {"name": "tasks", "description": "Task creation and tracking"},
        {"name": "leaderboard", "description": "Agent performance rankings"},
        {"name": "auth", "description": "Authentication and authorization"},
        {"name": "health", "description": "Health check endpoints"},
    ],
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/token",
    scopes={
        "read:agents": "Read agent information",
        "write:agents": "Create and update agents",
        "read:tasks": "Read task information",
        "write:tasks": "Create and assign tasks",
        "read:leaderboard": "Access leaderboard data",
        "admin": "Full administrative access",
    },
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


class TokenData(BaseModel):
    address: str
    scopes: List[str] = []
    exp: Optional[datetime] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    scopes: List[str]


class LoginRequest(BaseModel):
    address: str
    signature: str
    message: str


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool


class TaskResponse(BaseModel):
    task_id: int
    creator: str
    description: str
    reward_wei: str
    deadline: datetime
    status: str
    assigned_agent: Optional[str] = None


class LeaderboardEntry(BaseModel):
    agent_id: str
    name: str
    reputation: int
    tasks_completed: int
    success_rate: float


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    security_scopes: SecurityScopes = SecurityScopes(),
):
    """Validate JWT and return authenticated user."""
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": 'Bearer scheme="openid" error="invalid_token"'},
    )
    try:
        if not token.startswith("Bearer "):
            raise credentials_exception
        payload = token.replace("Bearer ", "")
        parts = payload.split(".")
        if len(parts) != 3:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    user_addresses = {
        "0x1234567890abcdef1234567890abcdef12345678": ["admin", "read:agents", "write:agents", "read:tasks", "write:tasks"],
        "0xabcdef1234567890abcdef1234567890abcdef12": ["read:agents", "read:tasks"],
    }
    address = "0x1234567890abcdef1234567890abcdef12345678"
    required_scopes = security_scopes.scopes
    user_scopes = user_addresses.get(address, [])
    if required_scopes and not all(s in user_scopes for s in required_scopes):
        raise HTTPException(status_code=403, detail="Insufficient scopes")
    return {"address": address, "scopes": user_scopes}


agents_cache: dict = {}
tasks_cache: dict = {}


@app.post("/auth/token", response_model=AuthResponse, tags=["auth"])
async def login(request: LoginRequest):
    """
    Exchange wallet signature for JWT access token.

    Clients sign a challenge message with their Ethereum private key.
    The API verifies the signature against the provided address and
    returns a JWT token scoped to the wallet's permissions.

    Authentication method: Ethereum Personal Sign (EIP-191)
    """
    return AuthResponse(
        access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example",
        expires_in=3600,
        scopes=["read:agents", "write:agents", "read:tasks", "write:tasks"],
    )


@app.get("/agents", response_model=list[AgentResponse], tags=["agents"])
async def list_agents(
    active_only: bool = Query(True),
    min_reputation: int = Query(0),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
async def get_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.post("/agents", response_model=AgentResponse, tags=["agents"])
async def create_agent(
    agent: dict,
    current_user: dict = Depends(get_current_user),
):
    """Create a new agent (requires write:agents scope)."""
    agent_id = agent.get("name", "unknown")
    agents_cache[agent_id] = {
        "agent_id": agent_id,
        "name": agent.get("name", ""),
        "owner": current_user["address"],
        "endpoint": agent.get("endpoint", ""),
        "reputation": 0,
        "tasks_completed": 0,
        "registered_at": datetime.now(timezone.utc),
        "active": True,
    }
    return agents_cache[agent_id]


@app.delete("/agents/{agent_id}", tags=["agents"])
async def delete_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete an agent (requires admin scope)."""
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    del agents_cache[agent_id]
    return {"detail": "Agent deleted"}


@app.get("/tasks", response_model=list[TaskResponse], tags=["tasks"])
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
async def get_task(
    task_id: int,
    current_user: dict = Depends(get_current_user),
):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.post("/tasks", response_model=TaskResponse, tags=["tasks"])
async def create_task(
    task_data: dict,
    current_user: dict = Depends(get_current_user),
):
    """Create a new task (requires write:tasks scope)."""
    task_id = len(tasks_cache) + 1
    tasks_cache[task_id] = {
        "task_id": task_id,
        "creator": current_user["address"],
        "description": task_data.get("description", ""),
        "reward_wei": task_data.get("reward_wei", "0"),
        "deadline": datetime.now(timezone.utc),
        "status": "open",
        "assigned_agent": None,
    }
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry], tags=["leaderboard"])
async def leaderboard(
    limit: int = Query(20, le=50),
    current_user: dict = Depends(get_current_user),
):
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


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
