"""
Test: CORS configuration for FastAPI app (#166)
"""

import os, sys
# Ensure api/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import pytest
from fastapi.testclient import TestClient
from main import app, origins

client = TestClient(app)

# We can't easily import TestClient without fastapi installed; verify endpoints exist.

def test_health_endpoint():
    """Health endpoint returns 200 and correct JSON shape."""
    response = client.get("/health")
    assert response.status_code == 200, f"Health failed with {response.status_code}"
    data = response.json()
    assert data["status"] == "ok"
    assert "agents_indexed" in data
    assert "tasks_indexed" in data
    print("✅ /health returns correct shape")

def test_cors_config_endpoint():
    """CORS config endpoint is exposed and returns expected fields."""
    response = client.get("/config/cors")
    assert response.status_code == 200, f"CORS config failed with {response.status_code}"
    data = response.json()
    assert "allow_origins" in data
    assert "allow_methods" in data
    assert data["allow_credentials"] is True
    assert data["allow_headers"] == "*"
    assert "GET" in data["allow_methods"]
    assert "POST" in data["allow_methods"]
    assert "OPTIONS" in data["allow_methods"]
    print("✅ /config/cors returns correct fields")

def test_cors_origins_default():
    """Default origins include local dev and prod domains."""
    assert any("localhost" in o for o in origins), "Localhost origin missing"
    assert any("openagents" in o for o in origins), "Prod origin missing"
    print("✅ Default origins configured")

def test_cors_env_override():
    """CORS_ORIGINS env var overrides defaults."""
    import importlib
    os.environ["CORS_ORIGINS"] = "https://custom.io,https://another.io"
    # Re-import to pick up env change
    import main
    importlib.reload(main)
    assert "https://custom.io" in main.origins
    assert "https://another.io" in main.origins
    os.environ.pop("CORS_ORIGINS", None)
    importlib.reload(main)
    print("✅ CORS_ORIGINS env override works")

if __name__ == "__main__":
    print("\n=== CORS Fix Tests (#166) ===\n")
    test_health_endpoint()
    test_cors_config_endpoint()
    test_cors_origins_default()
    test_cors_env_override()
    print("\n🎉 ALL TESTS PASSED\n")
