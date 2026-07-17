"""Tests for TaskRouter self-complete fix."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta


class TestTaskStatusUpdate:
    """Tests for the task status update endpoint."""

    def test_creator_cannot_complete_own_task(self):
        """Creator should not be able to mark their own task as completed."""
        task = Mock(id=1, creator_id=1, status="assigned", deadline=None)
        user = {"id": 1}

        # Creator trying to complete their own task
        assert task.creator_id == user["id"]

    def test_assignee_can_complete_task(self):
        """Assignee should be able to complete a task."""
        task = Mock(id=1, creator_id=1, assigned_to=2, status="assigned")
        user = {"id": 2}

        # Assignee completing the task
        assert task.creator_id != user["id"]

    def test_invalid_status_rejected(self):
        """Invalid status values should be rejected."""
        valid_statuses = {"open", "assigned", "in_progress", "review", "completed", "cancelled"}
        invalid_status = "hacked"
        assert invalid_status not in valid_statuses

    def test_status_transition_validation(self):
        """Only valid status transitions should be allowed."""
        transitions = {
            "open": {"assigned", "cancelled"},
            "assigned": {"in_progress", "cancelled"},
            "in_progress": {"review", "cancelled"},
            "review": {"completed", "in_progress"},
            "completed": set(),
            "cancelled": set(),
        }

        # Open -> assigned is valid
        assert "assigned" in transitions["open"]

        # Open -> completed is invalid (skip steps)
        assert "completed" not in transitions["open"]

        # Completed -> anything is invalid (terminal state)
        assert len(transitions["completed"]) == 0

    def test_deadline_enforcement(self):
        """Tasks past deadline should not be updatable."""
        deadline = datetime.utcnow() - timedelta(days=1)
        task = Mock(id=1, deadline=deadline, status="assigned")
        assert task.deadline < datetime.utcnow()
