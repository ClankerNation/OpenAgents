from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from sqlalchemy.orm import Session

from ..models.database import get_db, Agent, Task
from ..middleware.auth import get_current_user
from ..services.reputation import calculate_reputation_score

router = APIRouter(prefix="/reputation", tags=["reputation"])


@router.get("/{agent_id}")
async def get_reputation(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    score = calculate_reputation_score(
        tasks_completed=agent.tasks_completed,
        tasks_disputed=agent.tasks_disputed,
        total_task_time_hours=agent.total_task_time,
        last_activity=agent.last_activity_at,
    )

    return {
        "agent_id": agent.id,
        "name": agent.name,
        "reputation_score": score,
        "tasks_completed": agent.tasks_completed,
        "tasks_disputed": agent.tasks_disputed,
        "last_activity": agent.last_activity_at.isoformat(),
    }


@router.post("/update/{agent_id}")
async def update_reputation(
    agent_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.reputation = calculate_reputation_score(
        tasks_completed=agent.tasks_completed,
        tasks_disputed=agent.tasks_disputed,
        total_task_time_hours=agent.total_task_time,
        last_activity=agent.last_activity_at,
    )
    agent.last_activity_at = datetime.utcnow()
    db.commit()
    return {"agent_id": agent.id, "reputation": agent.reputation}


@router.get("/leaderboard")
async def reputation_leaderboard(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    agents = db.query(Agent).order_by(Agent.reputation.desc()).limit(limit).all()
    return [
        {
            "rank": i + 1,
            "agent_id": a.id,
            "name": a.name,
            "reputation": a.reputation,
            "tasks_completed": a.tasks_completed,
        }
        for i, a in enumerate(agents)
    ]
