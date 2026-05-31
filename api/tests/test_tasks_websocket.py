import os
import pathlib
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.routes import tasks as tasks_routes


class FakeTask:
    def __init__(self, task_id: int, status: str = "open", creator_id: int = 1):
        self.id = task_id
        self.status = status
        self.creator_id = creator_id
        self.updated_at = None


class FakeQuery:
    def __init__(self, task: FakeTask):
        self.task = task

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.task


class FakeDB:
    def __init__(self, task: FakeTask):
        self.task = task

    def query(self, _model):
        return FakeQuery(self.task)

    def commit(self):
        return None


@pytest.fixture(autouse=True)
def reset_task_ws_manager():
    tasks_routes.task_ws_manager._connections.clear()
    yield
    tasks_routes.task_ws_manager._connections.clear()


def build_client(task: FakeTask) -> TestClient:
    app = FastAPI()
    app.include_router(tasks_routes.router)

    fake_db = FakeDB(task)

    def override_get_current_user():
        return {"id": 1, "address": "0xabc"}

    def override_get_db():
        return fake_db

    app.dependency_overrides[tasks_routes.get_current_user] = override_get_current_user
    app.dependency_overrides[tasks_routes.get_db] = override_get_db

    return TestClient(app)


def test_websocket_subscribe_and_receive_task_update():
    task = FakeTask(task_id=1)
    client = build_client(task)

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.send_json({"action": "subscribe", "task_id": 1})
        assert websocket.receive_json() == {"type": "subscribed", "task_id": 1}

        response = client.patch("/tasks/1/status", json={"status": "in_progress"})
        assert response.status_code == 200

        message = websocket.receive_json()
        assert message["type"] == "task_update"
        assert message["task_id"] == 1
        assert message["status"] == "in_progress"


def test_unsubscribe_removes_task_subscription():
    task = FakeTask(task_id=1)
    client = build_client(task)

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.send_json({"action": "subscribe", "task_id": 1})
        assert websocket.receive_json() == {"type": "subscribed", "task_id": 1}
        assert tasks_routes.task_ws_manager.subscription_count(1) == 1

        websocket.send_json({"action": "unsubscribe", "task_id": 1})
        assert websocket.receive_json() == {"type": "unsubscribed", "task_id": 1}
        assert tasks_routes.task_ws_manager.subscription_count(1) == 0


def test_heartbeat_message_sent_to_connected_client():
    task = FakeTask(task_id=1)
    client = build_client(task)

    original_interval = tasks_routes.HEARTBEAT_INTERVAL_SECONDS
    tasks_routes.HEARTBEAT_INTERVAL_SECONDS = 0.01
    try:
        with client.websocket_connect("/tasks/ws") as websocket:
            message = websocket.receive_json()
            assert message["type"] == "heartbeat"
            assert "timestamp" in message
    finally:
        tasks_routes.HEARTBEAT_INTERVAL_SECONDS = original_interval


def test_disconnected_clients_are_cleaned_up():
    task = FakeTask(task_id=1)
    client = build_client(task)

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.send_json({"action": "subscribe", "task_id": 1})
        websocket.receive_json()
        assert tasks_routes.task_ws_manager.connection_count() == 1

    assert tasks_routes.task_ws_manager.connection_count() == 0
