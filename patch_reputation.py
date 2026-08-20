import re

# Patch database.py
with open('api/models/database.py', 'r') as f:
    db_content = f.read()

header = """\"\"\"
SQLAlchemy models and database session management.
@contributor-info ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
\"\"\"
"""
if not db_content.startswith('"""\nSQLAlchemy models and database session management.\n@contributor-info'):
    db_content = re.sub(r'^""".*?"""\s*', '', db_content, flags=re.DOTALL)
    db_content = header + db_content

old_agent = """    created_at = Column(DateTime, default=datetime.utcnow)

    # BUG: No cascade delete — deleting a user leaves orphaned agents"""
new_agent = """    created_at = Column(DateTime, default=datetime.utcnow)
    reputation = Column(Integer, default=500)
    tasks_completed = Column(Integer, default=0)
    tasks_disputed = Column(Integer, default=0)
    last_active_at = Column(DateTime, default=datetime.utcnow)

    # BUG: No cascade delete — deleting a user leaves orphaned agents"""
db_content = db_content.replace(old_agent, new_agent)

with open('api/models/database.py', 'w') as f:
    f.write(db_content)

# Patch agents.py
with open('api/routes/agents.py', 'r') as f:
    agents_content = f.read()

header2 = """\"\"\"
Agent CRUD endpoints for the OpenAgents platform.
@contributor-info ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
\"\"\"
"""
if not agents_content.startswith('"""\nAgent CRUD endpoints for the OpenAgents platform.\n@contributor-info'):
    agents_content = re.sub(r'^""".*?"""\s*', '', agents_content, flags=re.DOTALL)
    agents_content = header2 + agents_content

agents_content = agents_content.replace(
    'from datetime import datetime',
    'from datetime import datetime, timedelta'
)

reputation_code = """

def _apply_decay(agent):
    if not agent.last_active_at:
        return
    now = datetime.utcnow()
    weeks_inactive = (now - agent.last_active_at).days / 7.0
    if weeks_inactive > 0:
        decay = int(agent.reputation * 0.01 * weeks_inactive)
        agent.reputation = max(0, agent.reputation - decay)
        agent.last_active_at = now

@router.post("/{agent_id}/reputation/complete")
async def record_completion(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    _apply_decay(agent)
    agent.tasks_completed += 1
    total = agent.tasks_completed + agent.tasks_disputed
    rate = agent.tasks_completed / total if total > 0 else 1.0
    bonus = int(10 * rate)
    agent.reputation = min(1000, agent.reputation + bonus)
    agent.last_active_at = datetime.utcnow()
    db.commit()
    return {"id": agent.id, "reputation": agent.reputation}

@router.post("/{agent_id}/reputation/dispute")
async def record_dispute(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    _apply_decay(agent)
    agent.tasks_disputed += 1
    total = agent.tasks_completed + agent.tasks_disputed
    rate = agent.tasks_disputed / total if total > 0 else 1.0
    penalty = int(50 * rate)
    agent.reputation = max(0, agent.reputation - penalty)
    agent.last_active_at = datetime.utcnow()
    db.commit()
    return {"id": agent.id, "reputation": agent.reputation}

@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
):
    agents = db.query(Agent).all()
    for agent in agents:
        _apply_decay(agent)
    db.commit()
    
    sorted_agents = sorted(agents, key=lambda a: a.reputation, reverse=True)
    return [
        {
            "id": a.id,
            "name": a.name,
            "reputation": a.reputation,
            "tasks_completed": a.tasks_completed,
            "tasks_disputed": a.tasks_disputed,
        }
        for a in sorted_agents[:limit]
    ]
"""

if "@router.get(\"/leaderboard\")" not in agents_content:
    agents_content += reputation_code

with open('api/routes/agents.py', 'w') as f:
    f.write(agents_content)

print("Patched database.py and agents.py")
