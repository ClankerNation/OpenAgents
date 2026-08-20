"""
@fix-author rafaio1
@date 2026-08-20T00:00:00Z
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
@platform-instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
"""

"""Agent reputation scoring system with decay and leaderboard."""

import time
from typing import Optional

# In-memory store (placeholder for DB)
_reputation_store: dict[str, dict] = {}

MAX_SCORE = 1000
MIN_SCORE = 0
WEEKLY_DECAY_RATE = 0.01  # 1% per week
SECONDS_PER_WEEK = 7 * 24 * 60 * 60


def get_reputation(agent_id: str) -> dict:
    """Get current reputation score with decay applied."""
    if agent_id not in _reputation_store:
        return {"agent_id": agent_id, "score": 0, "last_updated": int(time.time())}
    
    entry = _reputation_store[agent_id]
    now = int(time.time())
    elapsed = now - entry["last_updated"]
    weeks_elapsed = elapsed / SECONDS_PER_WEEK
    
    # Apply exponential decay: score * (1 - rate)^weeks
    if weeks_elapsed > 0:
        decay_factor = (1 - WEEKLY_DECAY_RATE) ** weeks_elapsed
        current_score = max(MIN_SCORE, int(entry["score"] * decay_factor))
    else:
        current_score = entry["score"]
    
    return {
        "agent_id": agent_id,
        "score": current_score,
        "last_updated": entry["last_updated"],
        "tasks_completed": entry.get("tasks_completed", 0),
        "disputes": entry.get("disputes", 0),
    }


def update_on_completion(agent_id: str, success: bool, completion_time_seconds: float) -> dict:
    """Update reputation after task completion or dispute."""
    if agent_id not in _reputation_store:
        _reputation_store[agent_id] = {
            "score": 0,
            "last_updated": int(time.time()),
            "tasks_completed": 0,
            "disputes": 0,
        }
    
    entry = _reputation_store[agent_id]
    now = int(time.time())
    
    # Apply pending decay first
    elapsed = now - entry["last_updated"]
    weeks_elapsed = elapsed / SECONDS_PER_WEEK
    if weeks_elapsed > 0:
        decay_factor = (1 - WEEKLY_DECAY_RATE) ** weeks_elapsed
        entry["score"] = max(MIN_SCORE, int(entry["score"] * decay_factor))
    
    if success:
        # Reward: +50 base, bonus for speed (<1hr = +20, <24hr = +10)
        reward = 50
        if completion_time_seconds < 3600:
            reward += 20
        elif completion_time_seconds < 86400:
            reward += 10
        
        entry["score"] = min(MAX_SCORE, entry["score"] + reward)
        entry["tasks_completed"] = entry.get("tasks_completed", 0) + 1
    else:
        # Dispute penalty: -100
        entry["score"] = max(MIN_SCORE, entry["score"] - 100)
        entry["disputes"] = entry.get("disputes", 0) + 1
    
    entry["last_updated"] = now
    return get_reputation(agent_id)


def get_leaderboard(limit: int = 20) -> list[dict]:
    """Return sorted leaderboard by reputation score."""
    entries = []
    for agent_id in _reputation_store:
        rep = get_reputation(agent_id)
        entries.append(rep)
    
    entries.sort(key=lambda x: x["score"], reverse=True)
    return entries[:limit]
