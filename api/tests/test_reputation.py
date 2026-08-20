"""Tests for Agent Reputation Scoring System (Issue #43)."""
# @contributor-info ARO-Agentic
# @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
# @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash

import pytest
from fastapi.testclient import TestClient
from api.main import app, agents_cache
from datetime import datetime, timedelta

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_cache():
    agents_cache.clear()
    agents_cache["agent_1"] = {
        "agent_id": "agent_1",
        "name": "TestAgent",
        "owner": "0x123",
        "endpoint": "http://test.com",
        "reputation": 500,
        "tasks_completed": 0,
        "tasks_disputed": 0,
        "registered_at": datetime.utcnow(),
        "active": True,
        "last_active_at": datetime.utcnow()
    }
    yield
    agents_cache.clear()

def test_reputation_increases_on_completion():
    response = client.post("/agents/agent_1/reputation/complete")
    assert response.status_code == 200
    data = response.json()
    assert data["reputation"] > 500
    assert data["reputation"] <= 1000

def test_reputation_decreases_on_dispute():
    # First complete a task to have some history
    client.post("/agents/agent_1/reputation/complete")
    response = client.post("/agents/agent_1/reputation/dispute")
    assert response.status_code == 200
    data = response.json()
    # Reputation should decrease
    assert data["reputation"] < 1000

def test_leaderboard_returns_sorted_agents():
    # Add another agent with higher reputation
    agents_cache["agent_2"] = {
        "agent_id": "agent_2",
        "name": "TopAgent",
        "owner": "0x123",
        "endpoint": "http://test.com",
        "reputation": 900,
        "tasks_completed": 10,
        "tasks_disputed": 0,
        "registered_at": datetime.utcnow(),
        "active": True,
        "last_active_at": datetime.utcnow()
    }

    response = client.get("/leaderboard")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "TopAgent"
    assert data[0]["reputation"] >= data[1]["reputation"]

def test_reputation_bounds():
    # Try to push reputation above 1000
    for _ in range(100):
        client.post("/agents/agent_1/reputation/complete")
    
    assert agents_cache["agent_1"]["reputation"] <= 1000
