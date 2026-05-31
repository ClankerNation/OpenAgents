from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel

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


class AdminParameterUpdate(BaseModel):
    value: Any


class AdminUserUpdate(BaseModel):
    username: Optional[str] = None
    active: Optional[bool] = None
    roles: Optional[list[str]] = None


class AuditLogEntry(BaseModel):
    id: int
    action: str
    actor: str
    target: str
    before: Optional[Any] = None
    after: Optional[Any] = None
    timestamp: datetime
    ip: str


class AuditLogListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    records: list[AuditLogEntry]


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}
users_cache: dict = {}
admin_parameters: dict = {}
audit_logs: list[dict[str, Any]] = []
audit_log_seq = 0


def _record_audit(
    *,
    action: str,
    actor: str,
    target: str,
    before: Optional[Any],
    after: Optional[Any],
    request: Request,
) -> dict[str, Any]:
    global audit_log_seq
    audit_log_seq += 1
    ip = request.client.host if request.client else "unknown"
    record = {
        "id": audit_log_seq,
        "action": action,
        "actor": actor,
        "target": target,
        "before": deepcopy(before),
        "after": deepcopy(after),
        "timestamp": datetime.utcnow(),
        "ip": ip,
    }
    audit_logs.append(record)
    return record


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


@app.put("/admin/parameters/{parameter_name}")
async def update_admin_parameter(
    parameter_name: str,
    payload: AdminParameterUpdate,
    request: Request,
    actor: str = Header(..., alias="X-Admin-Actor"),
):
    before = deepcopy(admin_parameters.get(parameter_name))
    admin_parameters[parameter_name] = payload.value
    after = deepcopy(admin_parameters[parameter_name])
    record = _record_audit(
        action="parameter_update",
        actor=actor,
        target=f"parameter:{parameter_name}",
        before=before,
        after=after,
        request=request,
    )
    return {
        "parameter": parameter_name,
        "value": admin_parameters[parameter_name],
        "audit_id": record["id"],
    }


@app.put("/admin/users/{user_id}")
async def upsert_admin_user(
    user_id: str,
    payload: AdminUserUpdate,
    request: Request,
    actor: str = Header(..., alias="X-Admin-Actor"),
):
    before = deepcopy(users_cache.get(user_id))
    current = deepcopy(users_cache.get(user_id, {"user_id": user_id, "active": True, "roles": []}))
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        current[field] = value
    current["user_id"] = user_id
    users_cache[user_id] = current
    after = deepcopy(current)
    record = _record_audit(
        action="user_update",
        actor=actor,
        target=f"user:{user_id}",
        before=before,
        after=after,
        request=request,
    )
    return {"user": users_cache[user_id], "audit_id": record["id"]}


@app.get("/admin/audit-log", response_model=AuditLogListResponse)
async def list_admin_audit_log(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    records = audit_logs
    if actor:
        records = [record for record in records if record["actor"] == actor]
    if action:
        records = [record for record in records if record["action"] == action]
    if start_date:
        records = [record for record in records if record["timestamp"] >= start_date]
    if end_date:
        records = [record for record in records if record["timestamp"] <= end_date]
    return {
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "records": records[offset : offset + limit],
    }


@app.api_route("/admin/audit-log/{audit_id}", methods=["PUT", "PATCH", "DELETE"])
async def reject_audit_log_mutation(audit_id: int):
    raise HTTPException(status_code=405, detail="Audit log records are immutable")
