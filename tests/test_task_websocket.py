import os
import time

os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.models.database import Base, User
from api.routes.tasks import (
    router,
    task_ws_manager,
)
from api.routes.tasks import get_current_user, get_db


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _override_get_current_user():
    return {"id": 1, "address": "0xabc"}


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    return TestClient(app)


def _seed_user():
    db = TestingSessionLocal()
    try:
        existing = db.query(User).filter(User.id == 1).first()
        if not existing:
            db.add(User(id=1, address="0xabc", username="ws-test"))
            db.commit()
    finally:
        db.close()


def _reset_ws_manager_state():
    task_ws_manager.active_connections.clear()
    task_ws_manager.subscriptions.clear()
    task_ws_manager.connection_subscriptions.clear()
    for task in list(task_ws_manager.heartbeat_tasks.values()):
        task.cancel()
    task_ws_manager.heartbeat_tasks.clear()


def _create_task(client: TestClient) -> int:
    response = client.post(
        "/tasks/",
        json={
            "title": "ws test task",
            "description": "task for websocket validation",
            "reward_amount": 1.0,
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_websocket_subscribe_and_receive_task_update():
    _seed_user()
    _reset_ws_manager_state()
    client = _build_client()
    task_id = _create_task(client)

    with client.websocket_connect("/tasks/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        websocket.send_json({"action": "subscribe", "task_ids": [task_id]})
        subscribed = websocket.receive_json()
        assert subscribed["type"] == "subscribed"
        assert task_id in subscribed["task_ids"]

        response = client.patch(f"/tasks/{task_id}/status", json={"status": "in_progress"})
        assert response.status_code == 200

        update = websocket.receive_json()
        assert update["type"] == "task_update"
        assert update["task"]["id"] == task_id
        assert update["task"]["status"] == "in_progress"


def test_websocket_unsubscribe_stops_updates():
    _seed_user()
    _reset_ws_manager_state()
    client = _build_client()
    task_id = _create_task(client)

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.receive_json()
        websocket.send_json({"action": "subscribe", "task_ids": [task_id]})
        websocket.receive_json()

        websocket.send_json({"action": "unsubscribe", "task_ids": [task_id]})
        unsubscribed = websocket.receive_json()
        assert unsubscribed["type"] == "unsubscribed"
        assert task_id not in unsubscribed["task_ids"]

        response = client.patch(f"/tasks/{task_id}/status", json={"status": "review"})
        assert response.status_code == 200

        # No subscriber should remain for this task.
        assert task_id not in task_ws_manager.subscriptions


def test_websocket_heartbeat_and_disconnect_cleanup(monkeypatch):
    _seed_user()
    _reset_ws_manager_state()
    client = _build_client()

    monkeypatch.setattr("api.routes.tasks.HEARTBEAT_INTERVAL_SECONDS", 0.05)

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.receive_json()
        heartbeat = websocket.receive_json()
        assert heartbeat["type"] == "heartbeat"

    timeout_at = time.time() + 1.0
    while task_ws_manager.active_connections and time.time() < timeout_at:
        time.sleep(0.01)

    assert not task_ws_manager.active_connections
    assert not task_ws_manager.connection_subscriptions
