import pytest
from pydantic import ValidationError
from api.routes.agents import AgentCreate

def test_agent_create_valid_endpoint():
    agent = AgentCreate(name="Test Agent", endpoint="https://example.com/webhook")
    assert agent.endpoint == "https://example.com/webhook"

def test_agent_create_invalid_scheme():
    with pytest.raises(ValidationError):
        AgentCreate(name="Test Agent", endpoint="ftp://example.com")

def test_agent_create_ssrf_protection():
    with pytest.raises(ValidationError):
        AgentCreate(name="Test Agent", endpoint="http://localhost:8080")
    with pytest.raises(ValidationError):
        AgentCreate(name="Test Agent", endpoint="http://127.0.0.1/admin")
    with pytest.raises(ValidationError):
        AgentCreate(name="Test Agent", endpoint="http://192.168.1.1/internal")
    with pytest.raises(ValidationError):
        AgentCreate(name="Test Agent", endpoint="http://10.0.0.5/secret")
