import os
from fastapi import FastAPI, HTTPException, Query, Request, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from .middleware import auth

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

class RefreshRequest(BaseModel):
    refresh_token: str

class RevokeRequest(BaseModel):
    token: Optional[str] = None

@app.on_event("startup")
async def startup_event():
    env = os.getenv("ENV", "development").lower()
    if auth.is_jwt_secret_fallback and env != "development":
        raise RuntimeError("JWT_SECRET environment variable is missing in non-development environment!")


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


@app.post("/auth/refresh")
async def refresh_auth_token(body: RefreshRequest):
    token = body.refresh_token
    try:
        payload = auth.decode_token(token)
    except HTTPException as e:
        raise e
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
        
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
        
    jti = payload.get("jti")
    if jti:
        from .middleware.auth import revocation_store
        from datetime import datetime
        exp = payload.get("exp")
        if exp:
            expires_at = datetime.utcfromtimestamp(exp)
            revocation_store.revoke(jti, expires_at)
            
    user_id = payload.get("sub")
    address = payload.get("address")
    roles = payload.get("roles", [])
    
    if not user_id or not address:
        raise HTTPException(status_code=401, detail="Invalid token payload")
        
    new_tokens = auth.generate_login_tokens(user_id, address, roles)
    return new_tokens


@app.post("/auth/revoke")
async def revoke_auth_token(
    request: Request,
    body: Optional[RevokeRequest] = None,
):
    token = None
    if body:
        token = body.token
        
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(status_code=400, detail="Token must be provided in body or Authorization header")
        
    success = auth.revoke_token(token)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid token or failed to revoke")
        
    return {"message": "Token revoked successfully"}
