"""Tests for Structured Error Responses (Issue #202)."""
# @contributor-info ARO-Agentic
# @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
# @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_404_error_structure():
    response = client.get("/agents/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert "code" in data
    assert data["code"] == "NOT_FOUND"
    assert "message" in data
    assert "request_id" in data

def test_validation_error_structure():
    # Trigger validation error by passing invalid query param type
    response = client.get("/agents?limit=invalid")
    assert response.status_code == 400 or response.status_code == 422
    data = response.json()
    assert "code" in data
    assert data["code"] == "VALIDATION_ERROR"
    assert "details" in data
    assert "request_id" in data

def test_request_id_present_in_all_errors():
    r1 = client.get("/tasks/999999")
    # Use limit=100 which exceeds le=50 constraint on leaderboard
    r2 = client.get("/leaderboard?limit=100")
    
    d1 = r1.json()
    d2 = r2.json()
    
    assert "request_id" in d1
    assert "request_id" in d2
    # IDs should be unique per request
    if r1.status_code != 200 and r2.status_code != 200:
        assert d1["request_id"] != d2["request_id"]
