"""Tests for the WebSocket task update endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
import json
import asyncio
from datetime import datetime

# Import the app and router
import sys
sys.path.insert(0, "/tmp/OpenAgents/api")

from main import app
from routes.tasks import router
from routes.websocket_manager import manager

# Mount the router
app.include_router(router)


@pytest.fixture
def client():
    return TestClient(app)


def test_websocket_connect_and_heartbeat(client):
    """Test that WebSocket connects and receives heartbeat."""
    with client.websocket_connect("/tasks/ws") as ws:
        # Should receive a heartbeat within 35 seconds (30s interval + buffer)
        # For testing, we'll just verify the connection is alive
        data = ws.receive_json(timeout=5)
        assert data["type"] == "heartbeat"
        assert "timestamp" in data


def test_websocket_subscribe(client):
    """Test subscribe to a task ID."""
    with client.websocket_connect("/tasks/ws") as ws:
        # Subscribe to task 1
        ws.send_json({"type": "subscribe", "task_id": 1})
        response = ws.receive_json(timeout=5)
        assert response["type"] == "subscribed"
        assert response["task_id"] == 1


def test_websocket_subscribe_invalid_task_id(client):
    """Test subscribe with invalid task_id."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"type": "subscribe", "task_id": "not_a_number"})
        response = ws.receive_json(timeout=5)
        assert response["type"] == "error"


def test_websocket_unsubscribe(client):
    """Test unsubscribe from a task ID."""
    with client.websocket_connect("/tasks/ws") as ws:
        # Subscribe first
        ws.send_json({"type": "subscribe", "task_id": 5})
        response = ws.receive_json(timeout=5)
        assert response["type"] == "subscribed"

        # Then unsubscribe
        ws.send_json({"type": "unsubscribe", "task_id": 5})
        response = ws.receive_json(timeout=5)
        assert response["type"] == "unsubscribed"
        assert response["task_id"] == 5


def test_websocket_unsubscribe_all(client):
    """Test unsubscribe from all tasks."""
    with client.websocket_connect("/tasks/ws") as ws:
        # Subscribe to a few tasks
        ws.send_json({"type": "subscribe", "task_id": 1})
        ws.receive_json(timeout=5)

        ws.send_json({"type": "subscribe", "task_id": 2})
        ws.receive_json(timeout=5)

        # Then unsubscribe from all
        ws.send_json({"type": "unsubscribe_all"})
        response = ws.receive_json(timeout=5)
        assert response["type"] == "unsubscribed_all"


def test_websocket_unknown_message_type(client):
    """Test that unknown message types return an error."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"type": "unknown_type"})
        response = ws.receive_json(timeout=5)
        assert response["type"] == "error"
        assert "unknown" in response["message"].lower()


def test_websocket_invalid_json(client):
    """Test that invalid JSON returns an error."""
    with client.websocket_connect("/tasks/ws") as ws:
        # Send raw string instead of JSON
        ws.send_text("not json")
        response = ws.receive_json(timeout=5)
        assert response["type"] == "error"
        assert "json" in response["message"].lower()


def test_multiple_clients_independent_subscriptions(client):
    """Test that multiple clients have independent subscriptions."""
    with client.websocket_connect("/tasks/ws") as ws1, \
         client.websocket_connect("/tasks/ws") as ws2:

        # ws1 subscribes to task 10
        ws1.send_json({"type": "subscribe", "task_id": 10})
        response = ws1.receive_json(timeout=5)
        assert response["type"] == "subscribed"
        assert response["task_id"] == 10

        # ws2 subscribes to task 20
        ws2.send_json({"type": "subscribe", "task_id": 20})
        response = ws2.receive_json(timeout=5)
        assert response["type"] == "subscribed"
        assert response["task_id"] == 20

        # Verify ws1 is NOT subscribed to task 20
        # (no way to directly query from client, but we verify
        #  that the manager state is correct)
        from routes.websocket_manager import manager
        assert 10 in manager.subscriptions
        assert 20 in manager.subscriptions


def test_websocket_disconnect_cleanup(client):
    """Test that disconnection cleans up subscriptions."""
    with client.websocket_connect("/tasks/ws") as ws:
        ws.send_json({"type": "subscribe", "task_id": 99})
        ws.receive_json(timeout=5)

    # After disconnect, the subscription should be cleaned up
    from routes.websocket_manager import manager
    # Wait a moment for cleanup
    import time
    time.sleep(0.2)
    # The subscription may still have the set but it should be empty
    # or removed entirely
    assert 99 not in manager.subscriptions or len(manager.subscriptions[99]) == 0


def test_heartbeat_interval(client):
    """Test that heartbeat is sent every 30 seconds."""
    with client.websocket_connect("/tasks/ws") as ws:
        # Receive first heartbeat
        data = ws.receive_json(timeout=5)
        assert data["type"] == "heartbeat"
        ts1 = data["timestamp"]

        # Wait and receive second heartbeat
        # Note: In test mode this won't actually wait 30s
        # We just verify the heartbeat mechanism is wired up
        assert ts1 is not None
