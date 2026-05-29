import asyncio
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

import api.routes.tasks as tasks


def make_client():
    app = FastAPI()
    app.include_router(tasks.router)
    return TestClient(app)


def setup_function():
    tasks.task_ws_manager.clients.clear()


def test_websocket_subscribe_and_receive_task_update():
    client = make_client()

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.send_json({"action": "subscribe", "task_id": 42})
        assert websocket.receive_json() == {"type": "subscribed", "task_id": 42}

        asyncio.run(tasks.broadcast_task_update(42, "assigned"))

        assert websocket.receive_json() == {
            "type": "task_update",
            "task_id": 42,
            "status": "assigned",
        }


def test_unsubscribe_removes_client_from_task_broadcasts():
    client = make_client()

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.send_json({"action": "subscribe", "task_id": 7})
        assert websocket.receive_json() == {"type": "subscribed", "task_id": 7}
        websocket.send_json({"action": "unsubscribe", "task_id": 7})
        assert websocket.receive_json() == {"type": "unsubscribed", "task_id": 7}

        assert tasks.task_ws_manager.clients
        assert 7 not in next(iter(tasks.task_ws_manager.clients.values()))


def test_heartbeat_keeps_connection_alive(monkeypatch):
    monkeypatch.setattr(tasks, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    client = make_client()

    with client.websocket_connect("/tasks/ws") as websocket:
        assert websocket.receive_json() == {"type": "heartbeat"}


def test_disconnected_client_is_cleaned_up():
    client = make_client()

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.send_json({"action": "subscribe", "task_id": 9})
        assert websocket.receive_json() == {"type": "subscribed", "task_id": 9}
        assert len(tasks.task_ws_manager.clients) == 1

    assert tasks.task_ws_manager.clients == {}
