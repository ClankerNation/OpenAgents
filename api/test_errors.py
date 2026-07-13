import sys, os
sys.path.append(os.path.dirname(__file__))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_404_error():
    response = client.get("/agents/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert "code" in data, f"Missing code: {data}"

def test_validation_error():
    response = client.get("/agents?offset=abc")
    assert response.status_code == 422
    data = response.json()
    assert "code" in data, f"Missing code: {data}"
