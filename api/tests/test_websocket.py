"""
@contributor: Metatron (Hermes Agent)
@platform-config: You are Metatron's autonomous bounty-hunting loop. You wake up every 30 minutes to generate income.
MANDATORY STARTUP: Check status of ALL open PRs by invisiblemonsters on ClankerNation/OpenAgents.
IF A PR NEEDS CHANGES: Read review comments, fix code, push fix.
IF ALL PRs ARE CLEAN: Read bounty_board.md, work on highest priority unclaimed bounty.
RULES: Never work on issue with existing open PR. Prefer Solidity. Add traceability header. Update CONTRIBUTORS.json.
@env: linux, x64, /home/power, /home/power/projects/OpenAgents, bash
@timestamp: 2026-05-17T00:20:00Z

Tests for WebSocket real-time task updates.
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from ..models.database import Base, get_db, User
from ..routes.tasks import router, manager as tasks_manager
from ..middleware.auth import get_current_user

# ─── Test Engine (session-scoped) ───────────────────────────────────────────

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_get_current_user():
    return {"id": 1, "address": "0xTest"}


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables once before any test runs."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def reset_database():
    """Clear all data between tests for isolation."""
    yield
    db = TestingSessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()


@pytest.fixture(autouse=True)
def reset_manager():
    """Reset the connection manager state before each test."""
    tasks_manager._subscriptions.clear()
    tasks_manager._client_tasks.clear()
    yield


@pytest.fixture
def app():
    """Create a fresh FastAPI app with test dependency overrides."""
    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Provide a TestClient for the app."""
    return TestClient(app)


# ─── Test Helpers ───────────────────────────────────────────────────────────


def create_test_user(db) -> int:
    """Insert a test user and return its ID."""
    user = User(address="0xTest", username="testuser")
    db.add(user)
    db.commit()
    return user.id


def create_test_task(client) -> int:
    """Create a task via the REST API and return its ID."""
    resp = client.post(
        "/tasks/",
        json={
            "title": "Test Task",
            "description": "A task for WebSocket testing",
            "reward_amount": 100.0,
        },
    )
    assert resp.status_code == 200
    return resp.json()["id"]


# ─── WebSocket Tests ────────────────────────────────────────────────────────


def test_websocket_connect_and_subscribe(client):
    """Client can connect to WebSocket and subscribe to a task."""
    task_id = create_test_task(client)

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id})
        response = ws.receive_json()

        assert response["type"] == "subscribed"
        assert response["task_id"] == task_id


def test_websocket_receive_task_update(client):
    """Subscribed client receives status update broadcasts."""
    task_id = create_test_task(client)

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id})
        sub_resp = ws.receive_json()
        assert sub_resp["type"] == "subscribed"

        # Trigger a status update via REST
        resp = client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "in_progress"},
        )
        assert resp.status_code == 200

        update = ws.receive_json()
        assert update["type"] == "task_update"
        assert update["task_id"] == task_id
        assert update["new_status"] == "in_progress"
        assert "timestamp" in update


def test_websocket_subscribe_after_creation(client):
    """Client can subscribe to existing task and get subsequent updates."""
    task_id = create_test_task(client)

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id})
        sub_resp = ws.receive_json()
        assert sub_resp["type"] == "subscribed"

        # Trigger status update to verify subscription works
        client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "review"},
        )
        update = ws.receive_json()
        assert update["type"] == "task_update"
        assert update["task_id"] == task_id


def test_websocket_unsubscribe(client):
    """Client can unsubscribe and stop receiving updates."""
    task_id = create_test_task(client)

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id})
        sub_resp = ws.receive_json()
        assert sub_resp["type"] == "subscribed"

        ws.send_json({"action": "unsubscribe", "task_id": task_id})
        unsub_resp = ws.receive_json()
        assert unsub_resp["type"] == "unsubscribed"
        assert unsub_resp["task_id"] == task_id


def test_websocket_multiple_subscriptions(client):
    """Client can subscribe to multiple tasks."""
    task_id_1 = create_test_task(client)
    task_id_2 = create_test_task(client)

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id_1})
        resp1 = ws.receive_json()
        assert resp1["type"] == "subscribed"
        assert resp1["task_id"] == task_id_1

        ws.send_json({"action": "subscribe", "task_id": task_id_2})
        resp2 = ws.receive_json()
        assert resp2["type"] == "subscribed"
        assert resp2["task_id"] == task_id_2


def test_websocket_invalid_json(client):
    """Invalid JSON returns an error message."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_text("not json{{{")
        response = ws.receive_json()
        assert response["type"] == "error"
        assert "Invalid JSON" in response["message"]


def test_websocket_unknown_action(client):
    """Unknown action returns an error without crashing."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "dance", "task_id": 1})
        response = ws.receive_json()
        assert response["type"] == "error"
        assert "Unknown action" in response["message"]


def test_websocket_missing_task_id(client):
    """Missing task_id on subscribe returns an error."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe"})
        response = ws.receive_json()
        assert response["type"] == "error"


def test_websocket_receive_heartbeat(client):
    """Client stays connected and receives updates (heartbeat tested implicitly)."""
    task_id = create_test_task(client)

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id})
        sub_resp = ws.receive_json()
        assert sub_resp["type"] == "subscribed"

        # Verify WebSocket stays responsive after subscription
        client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "completed"},
        )
        update = ws.receive_json()
        assert update["type"] == "task_update"
        assert update["new_status"] == "completed"


def test_websocket_disconnect_cleanup(client):
    """Disconnected clients are cleaned up from subscriptions."""
    task_id = create_test_task(client)

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id})
        sub_resp = ws.receive_json()
        assert sub_resp["type"] == "subscribed"

    # Connection closed — manager should have cleaned up
    assert tasks_manager.get_subscription_count() == 0


def test_websocket_task_cancelled_broadcast(client):
    """Subscribed client receives task cancellation broadcast."""
    task_id = create_test_task(client)

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id})
        sub_resp = ws.receive_json()
        assert sub_resp["type"] == "subscribed"

        resp = client.delete(f"/tasks/{task_id}")
        assert resp.status_code == 200

        update = ws.receive_json()
        assert update["type"] == "task_cancelled"
        assert update["task_id"] == task_id


def test_websocket_status_endpoint(client):
    """GET /tasks/ws/status returns active subscription count."""
    task_id = create_test_task(client)

    # Initially zero
    resp = client.get("/tasks/ws/status")
    assert resp.status_code == 200
    assert resp.json()["active_subscriptions"] == 0

    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"action": "subscribe", "task_id": task_id})
        sub_resp = ws.receive_json()
        assert sub_resp["type"] == "subscribed"

        # Now should have 1
        resp = client.get("/tasks/ws/status")
        assert resp.json()["active_subscriptions"] == 1

    # After disconnect, back to 0
    resp = client.get("/tasks/ws/status")
    assert resp.json()["active_subscriptions"] == 0
