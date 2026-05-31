# @fix-author
# name: codex-c53d
# date: 2026-05-31
# platform_instructions: redacted (contains confidential system/developer preamble)
# @runtime
# os: windows
# arch: x64
# working_dir: F:/jiedan/OpenAgents-192-c53d
# shell: powershell

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Any, Optional
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


class AdminSettingUpdate(BaseModel):
    value: Any


class AdminUserRoleUpdate(BaseModel):
    role: str


class AuditLog(BaseModel):
    id: int
    action: str
    actor: str
    target: str
    before: Optional[Any] = None
    after: Optional[Any] = None
    timestamp: datetime
    ip: str


# In-memory store (placeholder for DB)
agents_cache: dict = {}
tasks_cache: dict = {}
admin_settings: dict[str, Any] = {}
admin_users: dict[str, dict[str, Any]] = {}
audit_logs: list[AuditLog] = []
_audit_log_seq = 0


def _next_audit_id() -> int:
    global _audit_log_seq
    _audit_log_seq += 1
    return _audit_log_seq


def _request_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _append_audit_log(
    *, action: str, actor: str, target: str, before: Any, after: Any, ip: str
) -> AuditLog:
    log = AuditLog(
        id=_next_audit_id(),
        action=action,
        actor=actor,
        target=target,
        before=before,
        after=after,
        timestamp=datetime.utcnow(),
        ip=ip,
    )
    audit_logs.append(log)
    return log


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


@app.put("/admin/settings/{setting_key}")
async def update_admin_setting(
    setting_key: str,
    update: AdminSettingUpdate,
    request: Request,
    actor: str = Header(..., alias="X-Admin-Actor"),
):
    before_value = admin_settings.get(setting_key)
    admin_settings[setting_key] = update.value
    _append_audit_log(
        action="settings.update",
        actor=actor,
        target=f"settings:{setting_key}",
        before=before_value,
        after=update.value,
        ip=_request_ip(request),
    )
    return {"setting": setting_key, "value": update.value}


@app.put("/admin/users/{user_id}/role")
async def update_admin_user_role(
    user_id: str,
    update: AdminUserRoleUpdate,
    request: Request,
    actor: str = Header(..., alias="X-Admin-Actor"),
):
    previous = admin_users.get(user_id)
    before_value = dict(previous) if previous else None
    updated_user = {"user_id": user_id, "role": update.role}
    admin_users[user_id] = updated_user
    _append_audit_log(
        action="user.role.update",
        actor=actor,
        target=f"user:{user_id}",
        before=before_value,
        after=updated_user,
        ip=_request_ip(request),
    )
    return updated_user


@app.get("/admin/audit-log", response_model=list[AuditLog])
async def list_admin_audit_logs(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    results = audit_logs
    if actor:
        results = [log for log in results if log.actor == actor]
    if action:
        results = [log for log in results if log.action == action]
    if start_date:
        results = [log for log in results if log.timestamp >= start_date]
    if end_date:
        results = [log for log in results if log.timestamp <= end_date]
    return results[offset : offset + limit]
