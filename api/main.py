// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
from fastapi import FastAPI, HTTPException, Query, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
import json
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

# Audit Log System (Immutable)
class AuditLogEntry(BaseModel):
    id: str = Field(..., example="550e8400-e29b-41d4-a716-446655440000")
    action: str = Field(..., example="UPDATE_AGENT")
    actor: str = Field(..., example="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
    target: str = Field(..., example="agent:0xabc123")
    before: Optional[dict] = Field(None, example={"reputation": 800})
    after: Optional[dict] = Field(None, example={"reputation": 850})
    ip_address: str = Field(..., example="192.168.1.1")
    timestamp: datetime = Field(..., example="2026-08-20T18:30:00Z")

# Immutable audit log storage (in-memory placeholder for DB)
audit_logs: List[AuditLogEntry] = []

def create_audit_log(
    request: Request,
    action: str,
    actor: str,
    target: str,
    before: dict = None,
    after: dict = None
) -> AuditLogEntry:
    """Create an immutable audit log entry. Records cannot be deleted or modified."""
    entry = AuditLogEntry(
        id=str(uuid.uuid4()),
        action=action,
        actor=actor,
        target=target,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else "unknown",
        timestamp=datetime.utcnow(),
    )
    audit_logs.append(entry)
    return entry

@app.get("/admin/audit-log", response_model=list[AuditLogEntry])
async def get_audit_log(
    request: Request,
    actor: Optional[str] = Query(None, description="Filter by actor address"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    start_date: Optional[str] = Query(None, description="Filter from date (ISO 8601)"),
    end_date: Optional[str] = Query(None, description="Filter to date (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Query audit logs with filtering. Logs are immutable and append-only."""
    results = list(audit_logs)
    
    # Apply filters
    if actor:
        results = [log for log in results if log.actor.lower() == actor.lower()]
    if action:
        results = [log for log in results if log.action.upper() == action.upper()]
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            results = [log for log in results if log.timestamp >= start_dt]
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            results = [log for log in results if log.timestamp <= end_dt]
        except ValueError:
            pass
    
    # Sort by timestamp descending (most recent first)
    results.sort(key=lambda x: x.timestamp, reverse=True)
    
    return results[offset : offset + limit]




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
