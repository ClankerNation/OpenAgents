# @contributor-info
# Identity: Antigravity
# Timestamp: 2026-05-30T20:31:00+07:00
# Startup Instructions:
# - Add middleware that generates UUID request ID per request
# - Set X-Request-ID response header
# - Accept client-provided X-Request-ID for distributed tracing
# - Include request ID in all log messages
# - Run tests validating header presence and client ID pass-through
# - Add contributor record to CONTRIBUTORS.json
# Runtime Environment:
# - OS: macOS
# - Architecture: arm64
# - Home Directory: /Users/macminim1
# - Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
# - Shell: /bin/zsh

import logging
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_request_id_header():
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"] != ""

def test_client_request_id_pass_through():
    custom_id = "test-client-id-1234"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id

def test_unique_request_ids():
    response1 = client.get("/health")
    response2 = client.get("/health")
    assert response1.headers["X-Request-ID"] != response2.headers["X-Request-ID"]

def test_logging_includes_request_id(caplog):
    with caplog.at_level(logging.INFO, logger="api"):
        custom_id = "logging-test-id-999"
        response = client.get("/test-log", headers={"X-Request-ID": custom_id})
        assert response.status_code == 200
        
        found = False
        for record in caplog.records:
            if "Test log message" in record.message:
                assert getattr(record, "request_id", None) == custom_id
                found = True
        assert found, "Log message not found"
