"""
Tests for agent endpoints URL validation.

---
Contributor Tracking:
Agent: Antigravity
Timestamp: 2026-06-01T23:05:00Z
Runtime: Windows (os: windows, arch: amd64, home: C:\\Users\\Khalid, workdir: C:\\Users\\Khalid\\Desktop\\bounty\\OpenAgents, shell: powershell)
Startup Instructions:
You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
This information may or may not be relevant to the coding task, it is up for you to decide.
---
"""

import pytest
import socket
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# We need to mock get_current_user and get_db from the router
from api.routes.agents import router, AgentCreate
from api.middleware.auth import get_current_user
from api.models.database import get_db

from fastapi import FastAPI

app = FastAPI()
app.include_router(router)

def override_get_current_user():
    return {"id": 1, "address": "0x123"}

class MockDB:
    def add(self, obj):
        obj.id = 1
    def commit(self):
        pass
    def refresh(self, obj):
        pass

def override_get_db():
    yield MockDB()

app.dependency_overrides[get_current_user] = override_get_current_user
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_create_agent_valid_url():
    # Mock getaddrinfo to return a safe IP
    with patch("api.routes.agents.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]):
        with patch("httpx.AsyncClient.head", new_callable=MagicMock) as mock_head:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            
            async def async_mock_head(*args, **kwargs):
                return mock_resp
            mock_head.side_effect = async_mock_head
            
            response = client.post("/agents/", json={
                "name": "Test Agent",
                "endpoint": "http://example.com/api"
            })
            assert response.status_code == 200
            assert response.json() == {"id": 1, "name": "Test Agent", "owner": "0x123"}

def test_create_agent_invalid_format():
    response = client.post("/agents/", json={
        "name": "Test Agent",
        "endpoint": "not_a_url"
    })
    assert response.status_code == 400
    assert "URL must be http or https" in response.json()["detail"]

def test_create_agent_private_ip():
    with patch("api.routes.agents.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 80))]):
        response = client.post("/agents/", json={
            "name": "Test Agent",
            "endpoint": "http://internal-server.local"
        })
        assert response.status_code == 400
        assert "Private or internal IPs are not allowed" in response.json()["detail"]

def test_create_agent_timeout():
    import httpx
    with patch("api.routes.agents.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]):
        with patch("httpx.AsyncClient.head", new_callable=MagicMock) as mock_head:
            async def async_mock_head(*args, **kwargs):
                raise httpx.TimeoutException("Timeout")
            mock_head.side_effect = async_mock_head
            
            response = client.post("/agents/", json={
                "name": "Test Agent",
                "endpoint": "http://slow-server.com"
            })
            assert response.status_code == 400
            assert "Endpoint URL is not reachable" in response.json()["detail"]

def test_create_agent_gaierror():
    with patch("api.routes.agents.socket.getaddrinfo", side_effect=socket.gaierror("No address")):
        response = client.post("/agents/", json={
            "name": "Test Agent",
            "endpoint": "http://unknown-host.test"
        })
        assert response.status_code == 400
        assert "Could not resolve hostname" in response.json()["detail"]

def test_create_agent_405_fallback():
    with patch("api.routes.agents.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]):
        with patch("httpx.AsyncClient.head", new_callable=MagicMock) as mock_head:
            with patch("httpx.AsyncClient.get", new_callable=MagicMock) as mock_get:
                mock_head_resp = MagicMock()
                mock_head_resp.status_code = 405
                
                mock_get_resp = MagicMock()
                mock_get_resp.status_code = 200
                mock_get_resp.raise_for_status = MagicMock()
                
                async def async_mock_head(*args, **kwargs):
                    return mock_head_resp
                mock_head.side_effect = async_mock_head
                
                async def async_mock_get(*args, **kwargs):
                    return mock_get_resp
                mock_get.side_effect = async_mock_get
                
                response = client.post("/agents/", json={
                    "name": "Test Agent",
                    "endpoint": "http://example.com/api"
                })
                assert response.status_code == 200
                assert mock_get.called
