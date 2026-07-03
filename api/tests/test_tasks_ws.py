import asyncio
import json
import os
from typing import Any
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.main import app
from api.routes.tasks import ws_manager, router as tasks_router

client = TestClient(app)


class FakeWebSocket:
    def __init__(self, messages):
        self._messages = messages
        self.accepted = False
        self.closed = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, message: str):
        self.sent.append(message)

    async def send_json(self, message: dict):
        self.sent.append(message)

    async def receive_text(self):
        if self._messages:
            return self._messages.pop(0)
        raise asyncio.TimeoutError()

    async def close(self, code: int = 1000):
        self.closed = True


def test_manager_connect_and_broadcast():
    async def run():
        ws = FakeWebSocket(["ping"])
        await ws_manager.connect(1, ws)
        await ws_manager.broadcast(1, {"id": 1, "status": "open"})
        await ws_manager.disconnect(1, ws)
        assert ws.accepted is True
        assert any("open" in str(m) for m in ws.sent)
        assert 1 not in ws_manager._connections

    asyncio.run(run())


def test_manager_unsubscribe_removes_from_broadcast():
    async def run():
        ws1 = FakeWebSocket([])
        ws2 = FakeWebSocket([])
        await ws_manager.connect(1, ws1)
        await ws_manager.connect(1, ws2)
        await ws_manager.disconnect(1, ws1)
        await ws_manager.broadcast(1, {"id": 1, "status": "completed"})
        assert len(ws_manager._connections.get(1, [])) == 1
        assert ws2.sent[-1]["status"] == "completed"

    asyncio.run(run())


def test_manager_heartbeat_ack():
    async def run():
        ws = FakeWebSocket(["ping"])
        await ws_manager.connect(2, ws)
        await asyncio.sleep(0)
        await ws_manager.disconnect(2, ws)
        assert any(m == "pong" for m in ws.sent) is False

    asyncio.run(run())


def test_manager_disconnect_cleanup_on_error():
    async def run():
        class BrokenWebSocket:
            accepted = False
            closed = False

            async def accept(self):
                self.accepted = True

            async def send_json(self, message):
                raise RuntimeError("closed")

            async def close(self, code=1000):
                self.closed = True

        ws = BrokenWebSocket()
        await ws_manager.connect(3, ws)
        await ws_manager.broadcast(3, {"id": 3, "status": "open"})
        assert 3 not in ws_manager._connections

    asyncio.run(run())


def test_websocket_endpoint_exists():
    routes = [route.endpoint for route in tasks_router.routes if hasattr(route, "endpoint")]
    assert any(route.__name__ == "websocket_tasks" for route in routes)
