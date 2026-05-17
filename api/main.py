@fix-author hermes-agent-deepseek-v4-pro
@date 2026-05-17T23:00:00Z
@init-context User goal: Generate $5+ from GitHub bounties. Session configured for Feishu messaging. Using GitHub PAT token with full repo access. Connected platforms: local, feishu.
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/root/hermes-agent, shell=bash
"""
OpenAgents API - off-chain indexer and agent discovery.
""" 
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
import uuid, logging
logger = logging.getLogger(__name__)

ERROR_CODES = {"VALIDATION_ERROR":"VALIDATION_ERROR","NOT_FOUND":"NOT_FOUND","AUTH_FAILED":"AUTH_FAILED","FORBIDDEN":"FORBIDDEN","RATE_LIMITED":"RATE_LIMITED","CONFLICT":"CONFLICT","INTERNAL_ERROR":"INTERNAL_ERROR"}

def error_response(code, message, details=None, status_code=500):
    return JSONResponse(status_code=status_code, content={"code":code,"message":message,"details":details or {}})

app = FastAPI(title="OpenAgents API", description="Off-chain indexer and agent discovery API", version="0.1.0")

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    m = {400:"VALIDATION_ERROR",401:"AUTH_FAILED",403:"FORBIDDEN",404:"NOT_FOUND",409:"CONFLICT",429:"RATE_LIMITED"}
    return error_response(m.get(exc.status_code,"INTERNAL_ERROR"), exc.detail, status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def val_exc(request: Request, exc: RequestValidationError):
    fe = {}
    for e in exc.errors(): fe[".".join(str(l) for l in e["loc"])] = e["msg"]
    return error_response("VALIDATION_ERROR","Request validation failed",{"fields":fe},422)

@app.exception_handler(Exception)
async def gen_exc(request: Request, exc: Exception):
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return error_response("INTERNAL_ERROR","An unexpected error occurred",status_code=500)

class AgentResponse(BaseModel):
    agent_id: str; name: str; owner: str; endpoint: str; reputation: int; tasks_completed: int; registered_at: datetime; active: bool

class TaskResponse(BaseModel):
    task_id: int; creator: str; description: str; reward_wei: str; deadline: datetime; status: str; assigned_agent: Optional[str] = None

class LeaderboardEntry(BaseModel):
    agent_id: str; name: str; reputation: int; tasks_completed: int; success_rate: float

agents_cache: dict = {}
tasks_cache: dict = {}

@app.get("/agents", response_model=list[AgentResponse])
async def list_agents(active_only: bool = Query(True), min_reputation: int = Query(0), limit: int = Query(50, le=100), offset: int = Query(0)):
    r = list(agents_cache.values())
    if active_only: r = [a for a in r if a.get("active")]
    r = [a for a in r if a.get("reputation",0) >= min_reputation]
    return r[offset:offset+limit]

@app.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    if agent_id not in agents_cache: raise HTTPException(404, "Agent not found")
    return agents_cache[agent_id]

@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(status: Optional[str] = Query(None), limit: int = Query(50, le=100), offset: int = Query(0)):
    r = list(tasks_cache.values())
    if status: r = [t for t in r if t.get("status") == status]
    return r[offset:offset+limit]

@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    if task_id not in tasks_cache: raise HTTPException(404, "Task not found")
    return tasks_cache[task_id]

@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=50)):
    entries = []
    for a in agents_cache.values():
        c = a.get("tasks_completed",0)
        entries.append({"agent_id":a["agent_id"],"name":a["name"],"reputation":a.get("reputation",0),"tasks_completed":c,"success_rate":c/max(c+1,1)})
    entries.sort(key=lambda x: x["reputation"], reverse=True)
    return entries[:limit]

@app.get("/health")
async def health():
    return {"status":"ok","agents_indexed":len(agents_cache),"tasks_indexed":len(tasks_cache),"timestamp":datetime.utcnow().isoformat()}
