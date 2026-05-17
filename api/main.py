"""
@contributor-info
identity: hermes-agent-olegc
timestamp: 2026-05-17T07:45:00Z
platform_instructions: Hermes Agent scheduled cron session for conservative paid open-source bounty work, GitHub PR workflow, autonomous validation, and concise Telegram delivery. Full private system/developer/session instructions are not embedded because they can contain confidential operational policy and credentials-handling rules.
runtime: os=Linux; arch=x86_64; home_dir=/home/olegc; working_dir=/home/olegc/bounty-work/OpenAgents; shell=/bin/bash
"""

from contextvars import ContextVar
from datetime import datetime
import logging
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

REQUEST_ID_HEADER = "X-Request-ID"
_request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_context.get()
        return True


class RequestIdFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id_context.get()
        return super().format(record)


request_id_filter = RequestIdFilter()
request_id_formatter = RequestIdFormatter("%(levelname)s:%(name)s:%(request_id)s:%(message)s")


def configure_request_id_logging() -> None:
    for logger_name in ("openagents.api", "uvicorn.access", "uvicorn.error"):
        configured_logger = logging.getLogger(logger_name)
        if request_id_filter not in configured_logger.filters:
            configured_logger.addFilter(request_id_filter)

        if not configured_logger.handlers:
            handler = logging.StreamHandler()
            configured_logger.addHandler(handler)

        for handler in configured_logger.handlers:
            handler.addFilter(request_id_filter)
            handler.setFormatter(request_id_formatter)

logger = logging.getLogger("openagents.api")
logger.setLevel(logging.INFO)
configure_request_id_logging()

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)


def _response_with_request_id(response: Response, request_id: str) -> Response:
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
    return _response_with_request_id(
        JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers),
        request_id,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> PlainTextResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
    logger.exception("request failed", extra={"path": request.url.path, "method": request.method})
    return _response_with_request_id(PlainTextResponse("Internal Server Error", status_code=500), request_id)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    configure_request_id_logging()
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
    token = _request_id_context.set(request_id)
    request.state.request_id = request_id

    try:
        logger.info("request started", extra={"path": request.url.path, "method": request.method})
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request completed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
            },
        )
        return response
    finally:
        _request_id_context.reset(token)


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
