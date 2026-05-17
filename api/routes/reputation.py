"""
@fix-author
  name: HermesAgent
  platform: Hermes Agent (haisui157)
  date: 2026-05-17
  task: Add agent reputation scoring system (issue #43)
  pre_conversation:
    You are HermesAgent, an autonomous bounty hunting AI agent running as a
    scheduled cron job on Hermes Agent for user haisui157.
  @runtime
    os: linux (WSL)
    arch: x86_64
    working_dir: /mnt/c/WINDOWS/System32
    shell: bash
"""
"""Reputation endpoints for agent scoring and leaderboard.

Provides endpoints to query agent reputation scores, the leaderboard,
and recalculate scores after lifecycle events.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user
from ..services.reputation import _compute_score, get_agent_rank

router = APIRouter(prefix="/reputation", tags=["reputation"])


@router.get("/leaderboard")
async def leaderboard(
    min_score: int = Query(0, ge=0, le=1000, description="Minimum reputation filter"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """Get the reputation leaderboard sorted by score descending.

    Returns paginated list of agents with reputation details:
    - rank, agent_id, name, reputation, tasks_completed,
      tasks_disputed, success_rate, last_active.
    """
    query = db.query(Agent).filter(Agent.reputation >= min_score)
    total = query.count()
    agents = (
        query.order_by(Agent.reputation.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    entries = []
    for rank_offset, agent in enumerate(agents, start=skip + 1):
        total_tasks = agent.tasks_completed + agent.tasks_disputed
        success_rate = (
            agent.tasks_completed / total_tasks if total_tasks > 0 else 0.0
        )
        entries.append({
            "rank": rank_offset,
            "agent_id": agent.id,
            "name": agent.name,
            "reputation": agent.reputation,
            "tasks_completed": agent.tasks_completed,
            "tasks_disputed": agent.tasks_disputed,
            "success_rate": round(success_rate, 4),
            "last_active": agent.last_active.isoformat() if agent.last_active else None,
        })

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "entries": entries,
    }


@router.get("/{agent_id}")
async def get_reputation(
    agent_id: int,
    db=Depends(get_db),
):
    """Get detailed reputation breakdown for a specific agent.

    Returns the full score breakdown including:
    - Current score, base, completion bonus, dispute penalty,
      timeliness bonus, decay deduction
    - Rank on leaderboard
    - Task statistics (completed, disputed, success rate)
    - Last active timestamp
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Build breakdown
    base = 500
    completion_bonus = agent.tasks_completed * 20
    dispute_penalty = agent.tasks_disputed * 30
    total = agent.tasks_completed + agent.tasks_disputed
    success_rate = agent.tasks_completed / total if total > 0 else 0.0
    timeliness_bonus = 10 if total > 0 and success_rate > 0.8 else 0
    
    rank = get_agent_rank(db, agent_id)

    return {
        "agent_id": agent.id,
        "name": agent.name,
        "rank": rank,
        "score": agent.reputation,
        "breakdown": {
            "base": base,
            "completion_bonus": completion_bonus,
            "dispute_penalty": -dispute_penalty,
            "timeliness_bonus": timeliness_bonus,
            "decay_deduction": base + completion_bonus - dispute_penalty + timeliness_bonus - agent.reputation,
        },
        "statistics": {
            "tasks_completed": agent.tasks_completed,
            "tasks_disputed": agent.tasks_disputed,
            "success_rate": round(success_rate, 4),
            "total_tasks": total,
        },
        "last_active": agent.last_active.isoformat() if agent.last_active else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


@router.post("/{agent_id}/recalculate")
async def recalculate_reputation(
    agent_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Trigger a reputation recalculation for an agent.

    Reapplies all scoring rules including decay and returns the new score.
    Only the agent's owner can trigger recalculation.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only the agent owner can recalculate reputation")

    new_score = _compute_score(agent)
    old_score = agent.reputation
    agent.reputation = new_score
    agent.last_active = datetime.utcnow()
    db.commit()
    db.refresh(agent)

    return {
        "agent_id": agent.id,
        "old_score": old_score,
        "new_score": new_score,
        "delta": new_score - old_score,
        "message": "Reputation recalculated successfully",
    }
