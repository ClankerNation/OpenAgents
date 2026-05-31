"""WebSocket tests for task real-time updates.

@contributor: openai-codex-55093
@platform-config: User-requested task execution for OpenAgents issue #188 in Codex.
@env: os=windows, arch=unknown, home_dir=C:\\Users\\55093, working_dir=F:\\jiedan\\OpenAgents-188, shell=powershell
@timestamp: 2026-05-31T05:24:40Z
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.routes import tasks as task_routes  # noqa: E402


@pytest.fixture
def client():
    task_routes.task_ws_manager = task_routes.TaskWebSocketManager()
    app = FastAPI()
    app.include_router(task_routes.router)

    @app.post("/_test/broadcast")
    async def _broadcast(payload: dict):
        await task_routes.task_ws_manager.broadcast_task_update(
            payload["task_id"], payload["status"]
        )
        return {"ok": True}

    @app.get("/_test/subscribers/{task_id}")
    async def _subscribers(task_id: int):
        count = sum(
            1
            for task_ids in task_routes.task_ws_manager._subscriptions.values()
            if task_id in task_ids
        )
        return {"task_id": task_id, "count": count}

    return TestClient(app)


def test_websocket_subscribe_and_receive_update(client):
    task_routes.HEARTBEAT_INTERVAL_SECONDS = 30

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.send_json({"action": "subscribe", "task_id": 42})
        assert websocket.receive_json() == {"type": "subscribed", "task_id": 42}

        response = client.post("/_test/broadcast", json={"task_id": 42, "status": "review"})
        assert response.status_code == 200

        assert websocket.receive_json() == {
            "type": "task_update",
            "task_id": 42,
            "status": "review",
        }


def test_websocket_unsubscribe_removes_from_broadcast(client):
    task_routes.HEARTBEAT_INTERVAL_SECONDS = 30

    with client.websocket_connect("/tasks/ws") as websocket:
        websocket.send_json({"action": "subscribe", "task_id": 7})
        assert websocket.receive_json() == {"type": "subscribed", "task_id": 7}
        assert client.get("/_test/subscribers/7").json()["count"] == 1

        websocket.send_json({"action": "unsubscribe", "task_id": 7})
        assert websocket.receive_json() == {"type": "unsubscribed", "task_id": 7}
        assert client.get("/_test/subscribers/7").json()["count"] == 0

        response = client.post("/_test/broadcast", json={"task_id": 7, "status": "completed"})
        assert response.status_code == 200


def test_websocket_heartbeat_ping(client):
    task_routes.HEARTBEAT_INTERVAL_SECONDS = 0.05

    with client.websocket_connect("/tasks/ws") as websocket:
        assert websocket.receive_json() == {"type": "heartbeat", "event": "ping"}
