"""Tests for WebSocket task updates (Issue #188)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
import jwt
import os
import json

os.environ["JWT_SECRET"] = "test_secret_long_enough_for_sha256_hashing"

from api.main import app
from api.models.database import Base, get_db, User, Task

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_ws.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def _get_user_token():
    payload = {
        "sub": "1",
        "address": "0xCreatorAddress",
        "roles": ["user"],
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")

def _setup_user_and_task():
    db = TestingSessionLocal()
    user = User(id=1, address="0xCreatorAddress", username="creator")
    db.add(user)
    db.commit()
    task = Task(
        id=100,
        title="Test Task",
        description="Test",
        reward_amount=10.0,
        status="open",
        creator_id=1,
        created_at=datetime.now(timezone.utc)
    )
    db.add(task)
    db.commit()
    db.close()

def test_websocket_connect_and_subscribe():
    _setup_user_and_task()
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "task_id": 100}))
        data = ws.receive_json()
        assert data["type"] == "subscribed"
        assert data["task_id"] == 100

def test_websocket_receive_update():
    _setup_user_and_task()
    token = _get_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "task_id": 100}))
        ws.receive_json() # consume subscribed msg
        
        # Trigger update via HTTP
        response = client.patch(
            "/tasks/100/status",
            json={"status": "in_progress"},
            headers=headers
        )
        assert response.status_code == 200
        
        # Receive broadcast (ignore pings)
        while True:
            data = ws.receive_json()
            if data["type"] == "task_update":
                break
        
        assert data["task_id"] == 100
        assert data["status"] == "in_progress"

def test_websocket_unsubscribe():
    _setup_user_and_task()
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "task_id": 100}))
        ws.receive_json()
        
        ws.send_text(json.dumps({"action": "unsubscribe", "task_id": 100}))
        data = ws.receive_json()
        assert data["type"] == "unsubscribed"
        assert data["task_id"] == 100
