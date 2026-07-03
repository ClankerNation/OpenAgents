"""
Tests for the WebSocket task updates endpoint /ws/tasks.

Verifies:
  - Authentication (missing/invalid token rejection)
  - Successful connection with valid token
  - Welcome message format
  - Ping/pong keepalive
  - Connection manager tracking
"""

import pytest
import json
import jwt
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from api.main import app
from api.middleware.auth import JWT_SECRET, JWT_ALGORITHM

client = TestClient(app)


# ---- Helper: generate a valid test token ----
def _make_token(user_id: str = "test-user-1", expired: bool = False) -> str:
    expire = datetime.utcnow() + (timedelta(hours=-1) if expired else timedelta(hours=1))
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


class TestWebSocketAuth:
    """WebSocket connection authentication tests."""

    def test_missing_token_rejected(self):
        """Connection without token should be rejected with code 4001."""
        with pytest.raises(Exception):
            with client.websocket_connect("/tasks/ws/tasks") as ws:
                ws.receive_text()

    def test_invalid_token_rejected(self):
        """Connection with an obviously invalid token should be rejected."""
        with pytest.raises(Exception):
            with client.websocket_connect(
                "/tasks/ws/tasks?token=not-a-real-jwt-token",
            ) as ws:
                ws.receive_text()

    def test_valid_token_accepted(self):
        """Connection with a valid token should succeed and get a welcome message."""
        token = _make_token()
        with client.websocket_connect(
            f"/tasks/ws/tasks?token={token}",
        ) as ws:
            data = ws.receive_text()
            msg = json.loads(data)
            assert msg["type"] == "connected"
            assert msg["user_id"] == "test-user-1"
            assert "message" in msg
            assert "timestamp" in msg


class TestWebSocketKeepalive:
    """WebSocket ping/pong keepalive tests."""

    def test_ping_pong(self):
        """Client ping should receive a pong response."""
        token = _make_token()
        with client.websocket_connect(
            f"/tasks/ws/tasks?token={token}",
        ) as ws:
            # Consume welcome
            ws.receive_text()
            # Send ping
            ws.send_text(json.dumps({"type": "ping"}))
            # Receive pong
            data = ws.receive_text()
            msg = json.loads(data)
            assert msg["type"] == "pong"
            assert "timestamp" in msg


class TestWebSocketConnectionManager:
    """Tests for the WebSocket connection manager."""

    def test_manager_tracking(self):
        """Connection manager should correctly track connection counts."""
        from api.routes.ws_manager import manager

        before = manager.active_connections
        token = _make_token()
        with client.websocket_connect(
            f"/tasks/ws/tasks?token={token}",
        ) as ws:
            # Consume welcome
            ws.receive_text()
            after = manager.active_connections
            assert after == before + 1, f"Expected {before + 1}, got {after}"

        # After disconnect, count should be back
        assert manager.active_connections == before

    def test_multiple_connections_tracked(self):
        """Multiple connections from the same user should all be tracked."""
        from api.routes.ws_manager import manager

        before = manager.active_connections
        token = _make_token()
        with client.websocket_connect(f"/tasks/ws/tasks?token={token}") as ws1, \
             client.websocket_connect(f"/tasks/ws/tasks?token={token}") as ws2:
            ws1.receive_text()  # welcome
            ws2.receive_text()  # welcome
            assert manager.active_connections == before + 2

        assert manager.active_connections == before

    def test_broadcast_reaches_connected_clients(self):
        """manager.broadcast should send messages to all connected clients."""
        from api.routes.ws_manager import manager

        before = manager.active_connections
        token = _make_token()
        with client.websocket_connect(f"/tasks/ws/tasks?token={token}") as ws1, \
             client.websocket_connect(f"/tasks/ws/tasks?token={token}") as ws2:
            ws1.receive_text()  # welcome
            ws2.receive_text()  # welcome

            # Broadcast manually using synchronous helper
            import asyncio
            asyncio.run(manager.broadcast({
                "type": "test_broadcast",
                "data": "hello",
            }))

            msg1 = json.loads(ws1.receive_text())
            msg2 = json.loads(ws2.receive_text())
            assert msg1["type"] == "test_broadcast"
            assert msg2["type"] == "test_broadcast"
            assert msg1["data"] == "hello"

    def test_broadcast_to_user(self):
        """manager.broadcast_to_user should only send to the specified user."""
        from api.routes.ws_manager import manager

        token1 = _make_token("user-alpha")
        token2 = _make_token("user-beta")

        with client.websocket_connect(f"/tasks/ws/tasks?token={token1}") as ws1, \
             client.websocket_connect(f"/tasks/ws/tasks?token={token2}") as ws2:
            ws1.receive_text()  # welcome
            ws2.receive_text()  # welcome

            import asyncio
            asyncio.run(manager.broadcast_to_user("user-alpha", {
                "type": "private_message",
                "data": "only for alpha",
            }))

            # user-alpha should receive it
            msg1 = json.loads(ws1.receive_text())
            assert msg1["type"] == "private_message"
            assert msg1["data"] == "only for alpha"

            # user-beta should NOT receive anything — verify connection is still open
            # but has no pending messages by trying to receive with a tiny timeout
            import threading, time
            received = []

            def try_receive():
                try:
                    data = ws2.receive_text()
                    received.append(data)
                except Exception:
                    received.append(None)

            t = threading.Thread(target=try_receive)
            t.daemon = True
            t.start()
            t.join(timeout=1.0)

            assert len(received) == 0 or received[0] is None, \
                f"user-beta should not receive messages, got: {received}"
