import re

with open('api/main.py', 'r') as f:
    content = f.read()

header = """\"\"\"
OpenAgents API Entry Point
@contributor-info ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
\"\"\"
"""
if not content.startswith('"""\nOpenAgents API Entry Point\n@contributor-info'):
    content = re.sub(r'^""".*?"""\s*', '', content, flags=re.DOTALL)
    content = header + content

# Add imports
old_imports = "from datetime import datetime"
new_imports = "from datetime import datetime, timedelta"
content = content.replace(old_imports, new_imports)

# Update AgentResponse to include new fields
old_agent_response = """class AgentResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    registered_at: datetime
    active: bool"""
new_agent_response = """class AgentResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    endpoint: str
    reputation: int
    tasks_completed: int
    tasks_disputed: int = 0
    registered_at: datetime
    active: bool
    last_active_at: Optional[datetime] = None"""
content = content.replace(old_agent_response, new_agent_response)

# Add reputation endpoints before the health check
reputation_endpoints = """

def _apply_decay(agent: dict) -> None:
    \"\"\"Apply 1% weekly decay to agent reputation.\"\"\"
    last_active = agent.get("last_active_at")
    if not last_active:
        return
    now = datetime.utcnow()
    weeks_inactive = (now - last_active).days / 7.0
    if weeks_inactive > 0:
        decay = int(agent.get("reputation", 500) * 0.01 * weeks_inactive)
        agent["reputation"] = max(0, agent.get("reputation", 500) - decay)
        agent["last_active_at"] = now


@app.post("/agents/{agent_id}/reputation/complete")
async def record_completion(agent_id: str):
    \"\"\"Record a successful task completion for an agent.\"\"\"
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents_cache[agent_id]
    _apply_decay(agent)
    
    agent["tasks_completed"] = agent.get("tasks_completed", 0) + 1
    total = agent["tasks_completed"] + agent.get("tasks_disputed", 0)
    rate = agent["tasks_completed"] / total if total > 0 else 1.0
    bonus = int(10 * rate)
    agent["reputation"] = min(1000, agent.get("reputation", 500) + bonus)
    agent["last_active_at"] = datetime.utcnow()
    
    return {"agent_id": agent_id, "reputation": agent["reputation"]}


@app.post("/agents/{agent_id}/reputation/dispute")
async def record_dispute(agent_id: str):
    \"\"\"Record a dispute against an agent.\"\"\"
    if agent_id not in agents_cache:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents_cache[agent_id]
    _apply_decay(agent)
    
    agent["tasks_disputed"] = agent.get("tasks_disputed", 0) + 1
    total = agent.get("tasks_completed", 0) + agent["tasks_disputed"]
    rate = agent["tasks_disputed"] / total if total > 0 else 1.0
    penalty = int(50 * rate)
    agent["reputation"] = max(0, agent.get("reputation", 500) - penalty)
    agent["last_active_at"] = datetime.utcnow()
    
    return {"agent_id": agent_id, "reputation": agent["reputation"]}

"""

# Insert before @app.get("/health")
content = content.replace('\n@app.get("/health")', reputation_endpoints + '\n@app.get("/health")')

# Update leaderboard to use decay and sort properly
old_leaderboard = """@app.get("/leaderboard", response_model=list[LeaderboardEntry])
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
    return entries[:limit]"""

new_leaderboard = """@app.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=50)):
    entries = []
    for agent in agents_cache.values():
        _apply_decay(agent)
        completed = agent.get("tasks_completed", 0)
        disputed = agent.get("tasks_disputed", 0)
        total = completed + disputed
        success_rate = completed / total if total > 0 else 0.0
        entries.append(
            {
                "agent_id": agent["agent_id"],
                "name": agent["name"],
                "reputation": agent.get("reputation", 0),
                "tasks_completed": completed,
                "success_rate": success_rate,
            }
        )
    entries.sort(key=lambda x: x["reputation"], reverse=True)
    return entries[:limit]"""

content = content.replace(old_leaderboard, new_leaderboard)

with open('api/main.py', 'w') as f:
    f.write(content)

print("Patched api/main.py with reputation system")
