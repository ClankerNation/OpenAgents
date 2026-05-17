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
"""Tests for the agent reputation scoring system.

Covers: score increases on success, score decreases on dispute,
weekly decay, leaderboard sorting, score bounds (0-1000),
and API endpoint integration.
"""

import pytest
import jwt
import os
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure JWT_SECRET is set for tests
os.environ.setdefault("JWT_SECRET", "test-secret-change-me-in-production")

from ..models.database import Base, Agent, User
from ..services.reputation import (
    _compute_score,
    _clamp_score,
    record_completion,
    record_dispute,
    apply_weekly_decay,
    get_agent_rank,
    BASE_REPUTATION,
    MIN_REPUTATION,
    MAX_REPUTATION,
    COMPLETION_POINTS,
    DISPUTE_PENALTY,
)
from ..main import app


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_agent(db_session):
    """Create a basic agent with default reputation (500)."""
    agent = Agent(
        name="test-agent",
        description="A test agent",
        owner_id=1,
        reputation=BASE_REPUTATION,
        tasks_completed=0,
        tasks_disputed=0,
        last_active=datetime.utcnow(),
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


@pytest.fixture
def setup_test_db(monkeypatch):
    """Override the DB session for API tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    
    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()
    
    monkeypatch.setattr("..routes.reputation.get_db", override_get_db)
    
    # Seed data
    session = TestSession()
    user = User(address="0x1234", username="testuser")
    session.add(user)
    session.commit()
    
    agents = [
        Agent(name="agent-alpha", owner_id=user.id, reputation=800, tasks_completed=15, tasks_disputed=1, last_active=datetime.utcnow()),
        Agent(name="agent-beta", owner_id=user.id, reputation=600, tasks_completed=8, tasks_disputed=2, last_active=datetime.utcnow()),
        Agent(name="agent-gamma", owner_id=user.id, reputation=900, tasks_completed=20, tasks_disputed=0, last_active=datetime.utcnow()),
        Agent(name="agent-delta", owner_id=user.id, reputation=300, tasks_completed=2, tasks_disputed=5, last_active=datetime.utcnow()),
    ]
    for a in agents:
        session.add(a)
    session.commit()
    session.close()
    
    return TestSession, user


# ── Score Computation Tests ────────────────────────────────────────────


def test_default_reputation(test_agent):
    """A newly created agent starts with base reputation of 500."""
    assert test_agent.reputation == BASE_REPUTATION


def test_score_increases_on_completion(test_agent):
    """Reputation increases when tasks are completed."""
    test_agent.tasks_completed = 5
    score = _compute_score(test_agent)
    expected = BASE_REPUTATION + (5 * COMPLETION_POINTS)
    assert score == expected


def test_score_decreases_on_dispute(test_agent):
    """Reputation decreases when tasks are disputed."""
    test_agent.tasks_disputed = 3
    score = _compute_score(test_agent)
    expected = BASE_REPUTATION - (3 * DISPUTE_PENALTY)
    assert score == expected


def test_score_net_high_competence(test_agent):
    """Agent with high completion and low dispute gets high score."""
    test_agent.tasks_completed = 20
    test_agent.tasks_disputed = 1
    score = _compute_score(test_agent)
    expected = BASE_REPUTATION + (20 * COMPLETION_POINTS) - (1 * DISPUTE_PENALTY) + 10  # +10 timeliness
    assert score == expected


def test_score_clamped_to_minimum(test_agent):
    """Score should not go below 0 even with many disputes."""
    test_agent.tasks_disputed = 1000
    score = _compute_score(test_agent)
    assert score >= MIN_REPUTATION


def test_score_clamped_to_maximum(test_agent):
    """Score should not exceed 1000 even with immense success."""
    test_agent.tasks_completed = 1000
    score = _compute_score(test_agent)
    assert score <= MAX_REPUTATION


def test_timeliness_bonus_applied(test_agent):
    """Agents with >80% success rate get timeliness bonus."""
    test_agent.tasks_completed = 10
    test_agent.tasks_disputed = 1  # ~91% success rate
    score = _compute_score(test_agent)
    expected = BASE_REPUTATION + (10 * COMPLETION_POINTS) - (1 * DISPUTE_PENALTY) + 10
    assert score == expected


def test_timeliness_bonus_not_applied_low_rate(test_agent):
    """Agents with <=80% success rate do NOT get timeliness bonus."""
    test_agent.tasks_completed = 8
    test_agent.tasks_disputed = 2  # 80% success rate — not >80%
    score = _compute_score(test_agent)
    expected = BASE_REPUTATION + (8 * COMPLETION_POINTS) - (2 * DISPUTE_PENALTY)
    assert score == expected


def test_no_tasks_no_bonus(test_agent):
    """Agent with no tasks gets no timeliness bonus (avoid div by zero)."""
    score = _compute_score(test_agent)
    assert score == BASE_REPUTATION


# ── Weekly Decay Tests ─────────────────────────────────────────────────


def test_no_decay_when_active(test_agent):
    """No decay if agent was active within the last 7 days."""
    test_agent.last_active = datetime.utcnow() - timedelta(days=3)
    test_agent.tasks_completed = 1
    score_before = test_agent.reputation
    test_agent.reputation = _compute_score(test_agent)
    # Decay should NOT apply
    expected = BASE_REPUTATION + COMPLETION_POINTS
    assert _compute_score(test_agent) == expected


def test_no_decay_recently_active(test_agent):
    """No decay if last_active is today."""
    test_agent.last_active = datetime.utcnow()
    test_agent.reputation = 700
    score = _compute_score(test_agent)
    # No decay since active within 7 days
    assert score == 700  # no completion, no dispute, no decay


def test_decay_applied_after_7_days(test_agent):
    """1% decay applied per week of inactivity."""
    test_agent.last_active = datetime.utcnow() - timedelta(days=14)
    test_agent.reputation = 500
    score = _compute_score(test_agent)
    # After 2 weeks: 500 * 0.99 * 0.99 = 490
    assert score == 490


def test_decay_compounds(test_agent):
    """Decay compounds across multiple weeks."""
    test_agent.last_active = datetime.utcnow() - timedelta(days=35)  # 5 weeks
    test_agent.reputation = 1000
    score = _compute_score(test_agent)
    # After 5 weeks: 1000 * 0.99^5 ≈ 951
    expected = int(1000 * (0.99 ** 5))
    assert score == expected


def test_no_decay_when_last_active_none(test_agent):
    """New agent with no last_active gets no decay."""
    test_agent.last_active = None
    score = _compute_score(test_agent)
    assert score == BASE_REPUTATION


# ── record_completion / record_dispute Tests ───────────────────────────


def test_record_completion_increases_score(db_session, test_agent):
    """record_completion should increment tasks_completed and recalculate."""
    record_completion(db_session, test_agent)
    assert test_agent.tasks_completed == 1
    expected = BASE_REPUTATION + COMPLETION_POINTS
    assert test_agent.reputation == expected


def test_record_dispute_decreases_score(db_session, test_agent):
    """record_dispute should increment tasks_disputed and recalculate."""
    record_dispute(db_session, test_agent)
    assert test_agent.tasks_disputed == 1
    expected = BASE_REPUTATION - DISPUTE_PENALTY
    assert test_agent.reputation == expected


def test_completion_and_dispute_cummulative(db_session, test_agent):
    """Multiple completions and disputes accumulate correctly."""
    for _ in range(5):
        record_completion(db_session, test_agent)
    for _ in range(2):
        record_dispute(db_session, test_agent)
    assert test_agent.tasks_completed == 5
    assert test_agent.tasks_disputed == 2
    expected = BASE_REPUTATION + (5 * COMPLETION_POINTS) - (2 * DISPUTE_PENALTY) + 10  # timeliness
    assert test_agent.reputation == expected


# ── Leaderboard Tests ──────────────────────────────────────────────────


def test_leaderboard_sorted_by_score(db_session):
    """Leaderboard returns agents sorted by reputation descending."""
    user = User(address="0xowner", username="owner")
    db_session.add(user)
    db_session.commit()
    
    agents = [
        Agent(name="low", owner_id=user.id, reputation=200, last_active=datetime.utcnow()),
        Agent(name="mid", owner_id=user.id, reputation=500, last_active=datetime.utcnow()),
        Agent(name="high", owner_id=user.id, reputation=800, last_active=datetime.utcnow()),
    ]
    for a in agents:
        db_session.add(a)
    db_session.commit()
    
    ranked = db_session.query(Agent).order_by(Agent.reputation.desc()).all()
    assert [a.name for a in ranked] == ["high", "mid", "low"]


def test_get_agent_rank(db_session):
    """get_agent_rank returns correct 1-indexed rank."""
    user = User(address="0xowner", username="owner")
    db_session.add(user)
    db_session.commit()
    
    agents = [
        Agent(name="a", owner_id=user.id, reputation=300, last_active=datetime.utcnow()),
        Agent(name="b", owner_id=user.id, reputation=700, last_active=datetime.utcnow()),
        Agent(name="c", owner_id=user.id, reputation=500, last_active=datetime.utcnow()),
    ]
    for a in agents:
        db_session.add(a)
    db_session.commit()
    
    rank_a = get_agent_rank(db_session, agents[0].id)  # 300 -> rank 3
    rank_b = get_agent_rank(db_session, agents[1].id)  # 700 -> rank 1
    rank_c = get_agent_rank(db_session, agents[2].id)  # 500 -> rank 2
    
    assert rank_a == 3
    assert rank_b == 1
    assert rank_c == 2


def test_get_agent_rank_nonexistent(db_session):
    """Non-existent agent returns rank -1."""
    rank = get_agent_rank(db_session, 99999)
    assert rank == -1


# ── API Integration Tests (requires monkeypatch for DB override) ────────


def test_leaderboard_endpoint_exists():
    """The /reputation/leaderboard route should be registered."""
    from ..routes.reputation import router
    paths = [r.path for r in router.routes]
    assert "/leaderboard" in paths


def test_get_reputation_endpoint_exists():
    """The /reputation/{agent_id} route should be registered."""
    from ..routes.reputation import router
    paths = [r.path for r in router.routes]
    assert "/{agent_id}" in paths or "/{agent_id}/" in paths


def test_recalculate_endpoint_exists():
    """The /reputation/{agent_id}/recalculate route should be registered."""
    from ..routes.reputation import router
    paths = [r.path for r in router.routes]
    assert "/{agent_id}/recalculate" in paths


# ── Clamp Tests ────────────────────────────────────────────────────────


def test_clamp_lower_bound():
    """Score should be clamped to MIN_REPUTATION."""
    assert _clamp_score(-100) == MIN_REPUTATION


def test_clamp_upper_bound():
    """Score should be clamped to MAX_REPUTATION."""
    assert _clamp_score(1500) == MAX_REPUTATION


def test_clamp_within_range():
    """Score within range should stay as is."""
    assert _clamp_score(500) == 500
    assert _clamp_score(0) == 0
    assert _clamp_score(1000) == 1000
