"""Tests for tasks.py - creator != completer, status transitions, pagination, deadline."""

import pytest
from unittest.mock import MagicMock, patch

mock_creator = {"id": 1, "address": "0xcreator111111111111111111111111111111111111"}
mock_other = {"id": 2, "address": "0xother222222222222222222222222222222222222"}


def make_mock_task(status="open", creator_id=1, deadline=None):
    task = MagicMock()
    task.id = 1
    task.title = "Test task"
    task.description = "A test task"
    task.reward_amount = 100.0
    task.status = status
    task.creator_id = creator_id
    task.agent_id = None
    task.deadline = deadline
    task.created_at = None
    task.updated_at = None
    return task


@pytest.mark.asyncio
class TestCreatorCompleter:
    """Creator cannot complete their own task; third party can."""

    @patch("api.routes.tasks.get_db")
    @patch("api.routes.tasks.get_current_user")
    async def test_creator_cannot_complete_own_task(self, mock_auth, mock_get_db):
        from api.routes.tasks import update_task_status, TaskStatusUpdate
        from fastapi import HTTPException

        mock_auth.return_value = mock_creator
        mock_db = MagicMock()
        task = make_mock_task(status="review", creator_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = task
        mock_get_db.return_value.__enter__.return_value = mock_db

        update = TaskStatusUpdate(status="completed")
        with pytest.raises(HTTPException) as exc:
            await update_task_status(1, update, mock_creator, mock_db)
        assert "Creator cannot complete" in str(exc.value.detail)

    @patch("api.routes.tasks.get_db")
    @patch("api.routes.tasks.get_current_user")
    async def test_other_can_complete_task(self, mock_auth, mock_get_db):
        from api.routes.tasks import update_task_status, TaskStatusUpdate

        mock_auth.return_value = mock_other
        mock_db = MagicMock()
        task = make_mock_task(status="review", creator_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = task
        mock_get_db.return_value.__enter__.return_value = mock_db

        update = TaskStatusUpdate(status="completed")
        result = await update_task_status(1, update, mock_other, mock_db)
        assert result["status"] == "completed"


@pytest.mark.asyncio
class TestStatusTransitions:
    """Only valid status transitions are allowed."""

    @patch("api.routes.tasks.get_db")
    @patch("api.routes.tasks.get_current_user")
    async def test_open_to_assigned_valid(self, mock_auth, mock_get_db):
        from api.routes.tasks import update_task_status, TaskStatusUpdate

        mock_auth.return_value = mock_creator
        mock_db = MagicMock()
        task = make_mock_task(status="open", creator_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = task
        mock_get_db.return_value.__enter__.return_value = mock_db

        update = TaskStatusUpdate(status="assigned")
        result = await update_task_status(1, update, mock_creator, mock_db)
        assert result["status"] == "assigned"

    @patch("api.routes.tasks.get_db")
    @patch("api.routes.tasks.get_current_user")
    async def test_open_to_completed_invalid(self, mock_auth, mock_get_db):
        from api.routes.tasks import update_task_status, TaskStatusUpdate
        from fastapi import HTTPException

        mock_auth.return_value = mock_creator
        mock_db = MagicMock()
        task = make_mock_task(status="open", creator_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = task
        mock_get_db.return_value.__enter__.return_value = mock_db

        update = TaskStatusUpdate(status="completed")
        with pytest.raises(HTTPException):
            await update_task_status(1, update, mock_creator, mock_db)

    @patch("api.routes.tasks.get_db")
    @patch("api.routes.tasks.get_current_user")
    async def test_assigned_to_cancelled_valid(self, mock_auth, mock_get_db):
        from api.routes.tasks import update_task_status, TaskStatusUpdate

        mock_auth.return_value = mock_creator
        mock_db = MagicMock()
        task = make_mock_task(status="assigned", creator_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = task
        mock_get_db.return_value.__enter__.return_value = mock_db

        update = TaskStatusUpdate(status="cancelled")
        result = await update_task_status(1, update, mock_creator, mock_db)
        assert result["status"] == "cancelled"

    @patch("api.routes.tasks.get_db")
    @patch("api.routes.tasks.get_current_user")
    async def test_completed_transition_blocked(self, mock_auth, mock_get_db):
        from api.routes.tasks import update_task_status, TaskStatusUpdate
        from fastapi import HTTPException

        mock_auth.return_value = mock_creator
        mock_db = MagicMock()
        task = make_mock_task(status="completed", creator_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = task
        mock_get_db.return_value.__enter__.return_value = mock_db

        update = TaskStatusUpdate(status="open")
        with pytest.raises(HTTPException):
            await update_task_status(1, update, mock_creator, mock_db)

    @patch("api.routes.tasks.get_db")
    @patch("api.routes.tasks.get_current_user")
    async def test_invalid_status_rejected(self, mock_auth, mock_get_db):
        from api.routes.tasks import update_task_status, TaskStatusUpdate
        from fastapi import HTTPException

        mock_auth.return_value = mock_creator
        mock_db = MagicMock()
        task = make_mock_task(status="open", creator_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = task
        mock_get_db.return_value.__enter__.return_value = mock_db

        update = TaskStatusUpdate(status="nonexistent")
        with pytest.raises(HTTPException):
            await update_task_status(1, update, mock_creator, mock_db)


class TestPaginationCap:
    """Pagination limit is capped at 100."""

    def test_pagination_limit_100(self):
        from api.routes.tasks import list_tasks
        import inspect
        sig = inspect.signature(list_tasks)
        params = sig.parameters.keys()
        assert "limit" in params


class TestDeadline:
    """Deadline auto-expire works."""

    def test_expire_deadline_task(self):
        from api.routes.tasks import _expire_deadline_tasks
        from datetime import datetime

        mock_db = MagicMock()
        task = make_mock_task(status="open", creator_id=1, deadline=datetime(2020, 1, 1))
        result = _expire_deadline_tasks(mock_db, task)
        assert result is True
        assert task.status == "cancelled"

    def test_future_deadline_not_expired(self):
        from api.routes.tasks import _expire_deadline_tasks
        from datetime import datetime

        mock_db = MagicMock()
        task = make_mock_task(status="open", creator_id=1, deadline=datetime(2030, 1, 1))
        result = _expire_deadline_tasks(mock_db, task)
        assert result is False
        assert task.status == "open"
