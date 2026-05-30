import logging
import os
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS configuration — resolved dynamically from environment variables
# ---------------------------------------------------------------------------
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
_allowed_origins = [
    origin.strip()
    for origin in _raw_origins.split(",")
    if origin.strip()
]

_app_env = os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "production")).lower()

# FastAPI strictly prohibits allow_credentials=True when allow_origins=["*"].
# In development mode with no explicit origins we fall back to a permissive
# wildcard but MUST disable credentials to avoid a runtime crash.
if not _allowed_origins and _app_env == "development":
    _allowed_origins = ["*"]
    _allow_credentials = False
else:
    # Production: require an explicit origin list with credentials enabled.
    _allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# ---------------------------------------------------------------------------
# Request ID tracing — async-safe via contextvars
# ---------------------------------------------------------------------------
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="N/A")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a unique trace token to every inbound request.

    If the client supplies an ``X-Request-ID`` header the value is preserved;
    otherwise a new hex UUID is generated.  The token is stored in a
    ``ContextVar`` so downstream handlers and log filters can read it safely
    across concurrent async tasks, and is echoed back on the response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_id = request.headers.get("X-Request-ID")
        rid = incoming_id if incoming_id else uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_ctx.reset(token)


app.add_middleware(RequestIDMiddleware)


# ---------------------------------------------------------------------------
# Logging — inject request_id into every log record
# ---------------------------------------------------------------------------
class RequestIDFilter(logging.Filter):
    """Reads the current request ID from the context variable and attaches
    it to each log record as ``record.request_id``."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("N/A")
        return True


_log_handler = logging.StreamHandler()
_log_handler.setFormatter(
    logging.Formatter("[%(request_id)s] %(levelname)s - %(message)s")
)
_log_handler.addFilter(RequestIDFilter())

logger = logging.getLogger("openagents")
logger.setLevel(logging.INFO)
logger.addHandler(_log_handler)


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
