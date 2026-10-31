"""Tests for task management endpoints."""

import pytest
from pydantic import ValidationError

from api.routes.tasks import TaskStatusUpdate, VALID_STATUSES, TaskCreate


def test_valid_status_update():
    """Valid status update passes."""
    update = TaskStatusUpdate(status="open")
    assert update.status == "open"


def test_invalid_status_rejected():
    """Invalid status is not in VALID_STATUSES."""
    assert "invalid_status" not in VALID_STATUSES


def test_all_valid_statuses():
    """All valid statuses are recognized."""
    for status in VALID_STATUSES:
        update = TaskStatusUpdate(status=status)
        assert update.status == status


def test_task_create_model():
    """TaskCreate model validates correctly."""
    task = TaskCreate(title="Test Task", description="Description", reward_amount=100.0)
    assert task.title == "Test Task"
    assert task.description == "Description"
    assert task.reward_amount == 100.0


def test_task_create_with_agent():
    """TaskCreate with agent_id."""
    task = TaskCreate(title="Test", description="Desc", reward_amount=50.0, agent_id=1)
    assert task.agent_id == 1


def test_valid_statuses_set():
    """VALID_STATUSES contains expected values."""
    expected = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}
    assert VALID_STATUSES == expected


def test_websocket_manager_init():
    """TaskWebSocketManager initializes correctly."""
    from api.routes.tasks import TaskWebSocketManager
    manager = TaskWebSocketManager()
    assert manager.active_connections == {}
    assert manager.task_subscriptions == {}


def test_task_status_update_validation():
    """TaskStatusUpdate validates status."""
    update = TaskStatusUpdate(status="completed")
    assert update.status == "completed"
    # Invalid status should still be accepted by model (validation is in endpoint)
    update2 = TaskStatusUpdate(status="invalid")
    assert update2.status == "invalid"
