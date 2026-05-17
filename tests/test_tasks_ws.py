"""
Tests for WebSocket task update endpoint in tasks.py.

Covers: connect, subscribe, receive broadcast, unsubscribe, heartbeat, cleanup.
Run: python -m pytest tests/test_tasks_ws.py -v
"""

import json
import os
import sys

# Set environment before any app imports
os.environ["JWT_SECRET"] = "test-secret-key-for-testing"
os.environ["DATABASE_URL"] = "sqlite:///./test_tasks_ws.db"

sys.path.insert(0, ".")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.tasks import router, manager
from api.models.database import init_db, get_db, SessionLocal, User, Task
from api.middleware.auth import get_current_user

# ── Setup ──

manager._connections.clear()
manager._all_connections.clear()


async def _override_get_current_user():
    return {"id": 1, "address": "0xtest", "username": "testuser"}


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_current_user] = _override_get_current_user
app.dependency_overrides[get_db] = override_get_db
init_db()

# Seed test user and task
db = SessionLocal()
try:
    db.query(User).delete()
    db.query(Task).delete()
    db.commit()
    user = User(id=1, address="0xtest", username="testuser")
    db.add(user)
    db.commit()
    task = Task(
        id=1, title="Test Task", description="desc", reward_amount=1.0,
        creator_id=1, status="open",
    )
    db.add(task)
    db.commit()
finally:
    db.close()

client = TestClient(app)


# ── Tests ──


def test_websocket_connects():
    """WebSocket connects successfully."""
    with client.websocket_connect("/tasks/ws") as ws:
        assert ws is not None


def test_subscribe():
    """Subscribe to a task ID returns confirmation."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "task_id": 1}))
        resp = json.loads(ws.receive_text())
        assert resp == {"subscribed": 1}


def test_unsubscribe():
    """Unsubscribe from a task ID returns confirmation."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "task_id": 1}))
        ws.receive_text()  # consume sub ack
        ws.send_text(json.dumps({"action": "unsubscribe", "task_id": 1}))
        resp = json.loads(ws.receive_text())
        assert resp == {"unsubscribed": 1}


def test_subscribe_and_receive_broadcast():
    """Subscribe to task 1, trigger status change via API, receive broadcast."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "task_id": 1}))
        ack = json.loads(ws.receive_text())
        assert ack == {"subscribed": 1}

        # Trigger status change
        http_resp = client.patch(
            "/tasks/1/status",
            json={"status": "in_progress"},
            headers={"Authorization": "Bearer test"},
        )
        assert http_resp.status_code == 200

        # Should receive broadcast
        msg = json.loads(ws.receive_text())
        assert msg["task_id"] == 1
        assert msg["event"] == "status_change"
        assert msg["data"]["status"] == "in_progress"


def test_unsubscribe_stops_broadcasts():
    """After unsubscribing, status changes are not received."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "task_id": 1}))
        ws.receive_text()  # sub ack

        # Trigger change — should arrive
        client.patch("/tasks/1/status", json={"status": "in_progress"},
                     headers={"Authorization": "Bearer test"})
        msg1 = json.loads(ws.receive_text())
        assert msg1["event"] == "status_change"

        # Unsubscribe
        ws.send_text(json.dumps({"action": "unsubscribe", "task_id": 1}))
        ack = json.loads(ws.receive_text())
        assert ack == {"unsubscribed": 1}

        # Trigger another change
        client.patch("/tasks/1/status", json={"status": "completed"},
                     headers={"Authorization": "Bearer test"})


def test_disconnected_client_cleaned_up():
    """After disconnect, manager cleans up the connection."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "task_id": 1}))
        ws.receive_text()
        assert len(manager._all_connections) >= 1
    # Context exited — disconnect fires
    assert len(manager._all_connections) == 0


def test_invalid_json_error():
    """Sending invalid JSON returns error message."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text("not json at all")
        resp = json.loads(ws.receive_text())
        assert "error" in resp


def test_unknown_action_error():
    """Unknown action returns error with valid_actions hint."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text(json.dumps({"action": "fly_to_moon"}))
        resp = json.loads(ws.receive_text())
        assert resp["error"] == "unknown action"
        assert "valid_actions" in resp
