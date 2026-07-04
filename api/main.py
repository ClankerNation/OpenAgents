from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from api.middleware.auth import (
    generate_login_tokens,
    create_access_token,
    decode_token,
    revoke_token,
    get_current_user,
    require_role,
)

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


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


class LoginRequest(BaseModel):
    user_id: str
    address: str
    roles: Optional[list] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RevokeRequest(BaseModel):
    token: str


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}


@app.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    active_only: bool = Query(True),
    min_reputation: int = Query(0),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    results = list(agents_cache.values())
    if active_only:
        results = [a for a in results if a.get("active")]
    results = [a for a in results if a.get("reputation", 0) >= min_reputation]
    return results[offset : offset + limit]


@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents_cache[agent_id]


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    results = list(tasks_cache.values())
    if status:
        results = [t for t in results if t.get("status") == status]
    return results[offset : offset + limit]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    if task_id not in tasks_cache:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_cache[task_id]


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=50)):
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
    return {
        "status": "ok",
        "agents_indexed": len(agents_cache),
        "tasks_indexed": len(tasks_cache),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/auth/login")
async def login(request: LoginRequest):
    tokens = generate_login_tokens(request.user_id, request.address, request.roles)
    return tokens


@app.post("/auth/refresh")
async def refresh(request: RefreshRequest):
    payload = decode_token(request.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    new_access = create_access_token(
        {
            "sub": payload.get("sub"),
            "address": payload.get("address"),
            "roles": payload.get("roles", []),
        }
    )
    return {"token": new_access, "expires_in": 60 * 60}


@app.post("/auth/revoke")
async def revoke(request: RevokeRequest):
    revoke_token(request.token)
    return {"message": "Token revoked"}


@app.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return user


@app.get("/admin/dashboard")
async def admin_dashboard(user: dict = Depends(require_role("admin"))):
    return {"user": user, "dashboard": "Welcome, admin"}
