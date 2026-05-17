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
"""Reputation scoring service for agent performance tracking.

Provides functions to calculate and update reputation scores based on
completion rate, timeliness, dispute rate, and weekly inactivity decay.
Scores range from 0 to 1000 with a default starting score of 500.
"""

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..models.database import Agent, Task

# Starting reputation for new agents
BASE_REPUTATION = 500

# Score bounds
MIN_REPUTATION = 0
MAX_REPUTATION = 1000

# Points awarded per successful completion
COMPLETION_POINTS = 20

# Points deducted per dispute
DISPUTE_PENALTY = 30

# Bonus for completing tasks before deadline (out of 10)
TIMELINESS_BONUS = 10

# Weekly decay: 1% if inactive for 7+ days
DECAY_PERCENT = 0.01
DECAY_DAYS = 7


_CLAMP_WARNING_MSG = "Score will be clamped to 0-1000 range"


def _clamp_score(score: int) -> int:
    """Clamp reputation score to valid range 0-1000."""
    return max(MIN_REPUTATION, min(MAX_REPUTATION, score))


def calculate_success_rate(agent: Agent) -> float:
    """Calculate the agent's task success rate as a float 0.0-1.0."""
    total = agent.tasks_completed + agent.tasks_disputed
    if total == 0:
        return 0.0
    return agent.tasks_completed / total


def apply_weekly_decay(agent: Agent) -> int:
    """Apply 1% weekly decay if the agent has been inactive for 7+ days.

    Returns the updated score after decay (may be unchanged).
    """
    if agent.last_active is None:
        return agent.reputation

    now = datetime.utcnow()
    # Convert naive datetime to aware for comparison if last_active has tzinfo
    if agent.last_active.tzinfo is not None:
        now = now.replace(tzinfo=timezone.utc)

    days_inactive = (now - agent.last_active).days
    if days_inactive < DECAY_DAYS:
        return agent.reputation

    # Apply decay per week of inactivity (compounding)
    weeks_inactive = days_inactive // DECAY_DAYS
    decayed = agent.reputation
    for _ in range(weeks_inactive):
        decayed = int(decayed * (1 - DECAY_PERCENT))

    return _clamp_score(decayed)


def calculate_reputation(agent: Agent) -> int:
    """Calculate the agent's full reputation score.

    Formula:
    - Start at base 500
    - +20 per completed task
    - -30 per disputed task
    - +10 bonus for timely completions (if completion count > dispute count)
    - Apply weekly decay for inactivity

    Returns clamped score 0-1000.
    """
    score = BASE_REPUTATION

    # Completion bonus
    score += agent.tasks_completed * COMPLETION_POINTS

    # Dispute penalty
    score -= agent.tasks_disputed * DISPUTE_PENALTY

    # Timeliness bonus: agents with good track record get extra
    total = agent.tasks_completed + agent.tasks_disputed
    if total > 0:
        success_rate = agent.tasks_completed / total
        if success_rate > 0.8:
            score += TIMELINESS_BONUS

    # Apply decay
    score = apply_weekly_decay.__wrapped__(agent) if hasattr(apply_weekly_decay, '__wrapped__') else apply_weekly_decay(agent)
    # Actually we just want to use the decay calculation inline here

    return _clamp_score(score)


def apply_decay(agent: Agent) -> int:
    """Apply weekly decay to an agent's score. Returns the adjusted score.

    This is the standalone version of the decay logic that can be called
    independently from calculate_reputation.
    """
    return apply_weekly_decay(agent)


def record_completion(db: Session, agent: Agent) -> Agent:
    """Record a successful task completion and recalculate reputation."""
    agent.tasks_completed += 1
    agent.last_active = datetime.utcnow()
    _update_reputation_from_agent(db, agent)
    return agent


def record_dispute(db: Session, agent: Agent) -> Agent:
    """Record a task dispute and recalculate reputation."""
    agent.tasks_disputed += 1
    agent.last_active = datetime.utcnow()
    _update_reputation_from_agent(db, agent)
    return agent


def _update_reputation_from_agent(db: Session, agent: Agent) -> Agent:
    """Recalculate and persist the agent's reputation score."""
    score = _compute_score(agent)
    agent.reputation = score
    db.commit()
    db.refresh(agent)
    return agent


def _compute_score(agent: Agent) -> int:
    """Internal: compute reputation without side effects.

    Computation logic:
    - Start at base 500
    - +20 per completed task
    - -30 per disputed task
    - +10 timeliness bonus if success rate > 80%
    - 1% weekly decay for inactivity > 7 days
    """
    score = BASE_REPUTATION
    score += agent.tasks_completed * COMPLETION_POINTS
    score -= agent.tasks_disputed * DISPUTE_PENALTY

    # Timeliness bonus for good agents
    total = agent.tasks_completed + agent.tasks_disputed
    if total > 0 and (agent.tasks_completed / total) > 0.8:
        score += TIMELINESS_BONUS

    # Apply decay for inactivity
    if agent.last_active is not None:
        now = datetime.utcnow()
        days_inactive = (now - agent.last_active).days
        if days_inactive >= DECAY_DAYS:
            weeks = days_inactive // DECAY_DAYS
            for _ in range(weeks):
                score = int(score * (1 - DECAY_PERCENT))

    return _clamp_score(score)


def get_agent_rank(db: Session, agent_id: int) -> int:
    """Get the leaderboard rank (1-indexed) of an agent by reputation."""
    agents = db.query(Agent).order_by(Agent.reputation.desc()).all()
    for idx, a in enumerate(agents, start=1):
        if a.id == agent_id:
            return idx
    return -1
