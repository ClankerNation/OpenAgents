"""Tests for WebSocket task updates."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from api.main import app
from api.routes.tasks import manager


@pytest.fixture(autouse=True)
def reset_manager():
    manager._connections.clear()
    manager._all_connections.clear()
    yield
    manager._connections.clear()
    manager._all_connections.clear()


class TestWebSocketConnection:
    def test_connect(self):
        client = TestClient(app)
        with client.websocket_connect("/tasks/ws") as ws:
            assert manager.connection_count == 1

    def test_disconnect(self):
        client = TestClient(app)
        with client.websocket_connect("/tasks/ws") as ws:
            pass
        assert manager.connection_count == 0

    def test_connect_with_task_id(self):
        client = TestClient(app)
        with client.websocket_connect("/tasks/ws?task_id=1") as ws:
            assert 1 in manager._connections
            assert len(manager._connections[1]) == 1


class TestWebSocketSubscribe:
    def test_subscribe_to_task(self):
        client = TestClient(app)
        with client.websocket_connect("/tasks/ws") as ws:
            ws.send_json({"action": "subscribe", "task_id": 42})
            assert 42 in manager._connections

    def test_unsubscribe_from_task(self):
        client = TestClient(app)
        with client.websocket_connect("/tasks/ws") as ws:
            ws.send_json({"action": "subscribe", "task_id": 42})
            assert 42 in manager._connections
            ws.send_json({"action": "unsubscribe", "task_id": 42})
            assert 42 not in manager._connections or len(manager._connections.get(42, set())) == 0


class TestWebSocketHeartbeat:
    def test_heartbeat_received(self):
        import time
        client = TestClient(app)
        with client.websocket_connect("/tasks/ws") as ws:
            time.sleep(31)
            data = ws.receive_json()
            assert data["type"] == "ping"
