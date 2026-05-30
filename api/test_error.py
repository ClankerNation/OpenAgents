# @contributor Antigravity
# @platform You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding. You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question. The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is. This information may or may not be relevant to the coding task, it is up for you to decide.
# @runtime OS: macOS, Architecture: arm64, Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents, Shell: /bin/zsh
# @date 2026-05-30T19:45:50+07:00

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.middleware.auth import generate_login_tokens

client = TestClient(app, raise_server_exceptions=False)

def verify_error_response(response, expected_status, expected_code):
    assert response.status_code == expected_status
    
    # Verify header is present
    assert "X-Request-ID" in response.headers
    request_id_header = response.headers["X-Request-ID"]
    assert request_id_header != ""
    
    # Verify body schema
    data = response.json()
    assert "code" in data
    assert "message" in data
    assert "details" in data
    assert "request_id" in data
    
    assert data["code"] == expected_code
    assert data["request_id"] == request_id_header
    return data

def test_validation_error():
    # Trigger validation error on limit (e.g. limit > 100 on /agents)
    res = client.get("/agents?limit=1000")
    data = verify_error_response(res, 422, "VALIDATION_ERROR")
    # Verify field-level details
    assert "query.limit" in data["details"]

def test_not_found_error():
    # Trigger 404
    res = client.get("/non-existent-route-for-testing-purposes-12345")
    verify_error_response(res, 404, "NOT_FOUND")

def test_auth_failed_401():
    # Trigger 401: calling auth-required route without headers
    res = client.post("/admin/config", json={"key": "test", "value": "val"})
    verify_error_response(res, 401, "AUTH_FAILED")

def test_auth_failed_403():
    # Trigger 403: calling auth-required route with non-admin token
    non_admin = generate_login_tokens(user_id="2", address="0xUser", roles=["user"])
    headers = {"Authorization": f"Bearer {non_admin['token']}"}
    res = client.post("/admin/config", json={"key": "test", "value": "val"}, headers=headers)
    verify_error_response(res, 403, "AUTH_FAILED")

def test_rate_limited():
    # Trigger 429 using the special test endpoint
    res = client.get("/test-error/429")
    verify_error_response(res, 429, "RATE_LIMITED")

def test_internal_error():
    # Trigger 500 using the special test endpoint
    res = client.get("/test-error/500")
    verify_error_response(res, 500, "INTERNAL_ERROR")
