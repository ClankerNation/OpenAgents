"""
@contributor: hermes-agent
@platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
@env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
@timestamp: 2026-05-18
"""

"""Tests for WebSocket task update endpoint and TaskBroadcaster."""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set required env vars before importing the app modules
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")

from starlette.testclient import TestClient
from fastapi import FastAPI

from api.routes.tasks import router, broadcaster, TaskBroadcaster


# ---------------------------------------------------------------------------
# Helper: Create a minimal FastAPI app that includes the tasks router
# ---------------------------------------------------------------------------

def _create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Unit tests for TaskBroadcaster
# ---------------------------------------------------------------------------

class TestTaskBroadcasterUnit:
    """Pure unit tests for the TaskBroadcaster class (no real WebSocket)."""

    def setup_method(self):
        self.b = TaskBroadcaster()

    @pytest.mark.asyncio
    async def test_connect_adds_client(self):
        ws = AsyncMock()
        ws.client = ("127.0.0.1", 1234)
        await self.b.connect(ws)
        assert self.b.connection_count == 1
        assert self.b.get_subscriptions(ws) == set()

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        ws = AsyncMock()
        ws.client = ("127.0.0.1", 1234)
        await self.b.connect(ws)
        assert self.b.connection_count == 1
        await self.b.disconnect(ws)
        assert self.b.connection_count == 0

    @pytest.mark.asyncio
    async def test_subscribe(self):
        ws = AsyncMock()
        ws.client = ("127.0.0.1", 1234)
        await self.b.connect(ws)
        await self.b.subscribe(ws, 42)
        assert self.b.is_subscribed(ws, 42)
        assert not self.b.is_subscribed(ws, 99)

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        ws = AsyncMock()
        ws.client = ("127.0.0.1", 1234)
        await self.b.connect(ws)
        await self.b.subscribe(ws, 42)
        assert self.b.is_subscribed(ws, 42)
        await self.b.unsubscribe(ws, 42)
        assert not self.b.is_subscribed(ws, 42)

    @pytest.mark.asyncio
    async def test_broadcast_to_subscribed_client(self):
        ws = AsyncMock()
        ws.client = ("127.0.0.1", 1234)
        await self.b.connect(ws)
        await self.b.subscribe(ws, 42)
        await self.b.broadcast_state_change(42, {"status": "completed", "title": "T"})
        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["type"] == "task_update"
        assert msg["task_id"] == 42
        assert msg["status"] == "completed"

    @pytest.mark.asyncio
    async def test_broadcast_not_sent_to_unsubscribed(self):
        ws1 = AsyncMock()
        ws1.client = ("127.0.0.1", 1234)
        ws2 = AsyncMock()
        ws2.client = ("127.0.0.1", 5678)
        await self.b.connect(ws1)
        await self.b.connect(ws2)
        await self.b.subscribe(ws1, 42)
        await self.b.subscribe(ws2, 99)
        await self.b.broadcast_state_change(42, {"status": "completed"})
        # ws1 should get it (subscribed to 42)
        ws1.send_text.assert_called_once()
        # ws2 should NOT get it (only subscribed to 99)
        ws2.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_no_subscription_clients(self):
        """Clients with no subscriptions should receive all updates."""
        ws = AsyncMock()
        ws.client = ("127.0.0.1", 1234)
        await self.b.connect(ws)
        # No subscription — receive-all mode
        await self.b.broadcast_state_change(42, {"status": "completed"})
        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["task_id"] == 42

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_subscriptions(self):
        ws = AsyncMock()
        ws.client = ("127.0.0.1", 1234)
        await self.b.connect(ws)
        await self.b.subscribe(ws, 1)
        await self.b.subscribe(ws, 2)
        await self.b.disconnect(ws)
        assert self.b.connection_count == 0
        assert self.b.get_subscriptions(ws) == set()

    @pytest.mark.asyncio
    async def test_broadcast_removes_broken_connection(self):
        """If sending fails, the client should be disconnected automatically."""
        ws = AsyncMock()
        ws.client = ("127.0.0.1", 1234)
        await self.b.connect(ws)
        await self.b.subscribe(ws, 1)
        # Make send_text raise an exception
        ws.send_text.side_effect = RuntimeError("Connection lost")
        await self.b.broadcast_state_change(1, {"status": "completed"})
        # Should have cleaned up
        assert self.b.connection_count == 0


# ---------------------------------------------------------------------------
# Integration tests using TestClient WebSocket context
# ---------------------------------------------------------------------------

class TestWebSocketEndpoint:
    """Integration tests for the /tasks/ws endpoint."""

    def setup_method(self):
        self.app = _create_app()
        self.client = TestClient(self.app)

    def test_connect_and_disconnect(self):
        """Client can connect and disconnect cleanly."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            pass  # just connecting and closing is fine
        # After disconnect, broadcaster should have 0 connections
        assert broadcaster.connection_count == 0

    def test_subscribe_to_task(self):
        """Client can subscribe to a specific task and receives confirmation."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "task_id": 42}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "subscribed"
            assert response["task_id"] == 42

    def test_unsubscribe_from_task(self):
        """Client can unsubscribe from a specific task and receives confirmation."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "task_id": 42}))
            ws.receive_text()  # consume subscribed confirmation
            ws.send_text(json.dumps({"action": "unsubscribe", "task_id": 42}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "unsubscribed"
            assert response["task_id"] == 42

    def test_receive_update_after_subscribe(self):
        """Subscribed client receives task_update when broadcast fires."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "task_id": 7}))
            ws.receive_text()  # consume subscribed confirmation

            # Manually broadcast to task 7
            asyncio.get_event_loop().run_until_complete(
                broadcaster.broadcast_state_change(7, {"status": "completed", "title": "Test task"})
            )

            # We should receive the task_update message
            # Note: there might be ping messages interleaved, so we filter
            received = None
            for _ in range(5):
                msg = json.loads(ws.receive_text())
                if msg.get("type") == "task_update":
                    received = msg
                    break
            assert received is not None
            assert received["task_id"] == 7
            assert received["status"] == "completed"

    def test_heartbeat_pong(self):
        """Client can send ping and receive pong response."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            ws.send_text(json.dumps({"action": "ping"}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "pong"

    def test_invalid_json(self):
        """Server responds with error for invalid JSON."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            ws.send_text("not json")
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"
            assert "Invalid JSON" in response["detail"]

    def test_unknown_action(self):
        """Server responds with error for unknown action."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            ws.send_text(json.dumps({"action": "unknown"}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"

    def test_subscribe_without_task_id(self):
        """Subscribe without task_id returns an error."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            ws.send_text(json.dumps({"action": "subscribe"}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"
            assert "task_id required" in response["detail"]

    def test_cleanup_on_disconnect(self):
        """Disconnection removes client from broadcaster."""
        with self.client.websocket_connect("/tasks/ws") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "task_id": 1}))
            ws.receive_text()  # consume confirmation
        # After disconnect, broadcaster should reflect 0 connections
        assert broadcaster.connection_count == 0