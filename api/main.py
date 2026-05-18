from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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


# ── JWT refresh and revocation endpoints ──
from api.middleware.auth import (
    generate_login_tokens,
    refresh_access_token,
    revoke_token,
    is_token_revoked,
    get_current_user,
)


class LoginRequest(BaseModel):
    user_id: str
    address: str
    roles: Optional[list[str]] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RevokeRequest(BaseModel):
    token: str


@app.post("/auth/login", status_code=200)
async def auth_login(req: LoginRequest):
    """Generate access + refresh token pair."""
    tokens = generate_login_tokens(req.user_id, req.address, req.roles)
    return tokens


@app.post("/auth/refresh", status_code=200)
async def auth_refresh(req: RefreshRequest):
    """Exchange a valid refresh token for a new access token. Old refresh token is revoked."""
    try:
        new_access = refresh_access_token(req.refresh_token)
        return {"token": new_access}
    except HTTPException:
        raise


@app.post("/auth/revoke", status_code=200)
async def auth_revoke(req: RevokeRequest, user: dict = Depends(get_current_user)):
    """Revoke a token so it can no longer be used. Requires authentication."""
    revoke_token(req.token)
    return {"status": "revoked"}


@app.get("/auth/check", status_code=200)
async def auth_check(token: str = Query(...), _user: dict = Depends(get_current_user)):
    """Check if a token has been revoked. Requires authentication."""
    return {"revoked": is_token_revoked(token)}
