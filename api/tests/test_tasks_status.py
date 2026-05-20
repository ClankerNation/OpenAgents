from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes.tasks import expire_if_deadline_passed, validate_status_transition


def task(status="review", creator_id=1, deadline=None):
    return SimpleNamespace(status=status, creator_id=creator_id, deadline=deadline, updated_at=None)


def test_creator_cannot_complete_own_task():
    with pytest.raises(HTTPException) as exc:
        validate_status_transition(task(status="review", creator_id=1), "completed", user_id=1)

    assert exc.value.status_code == 403


def test_non_creator_can_complete_review_task():
    validate_status_transition(task(status="review", creator_id=1), "completed", user_id=2)


def test_invalid_status_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_status_transition(task(status="open", creator_id=1), "bogus", user_id=1)

    assert exc.value.status_code == 400


def test_invalid_transition_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_status_transition(task(status="open", creator_id=1), "completed", user_id=2)

    assert exc.value.status_code == 400


def test_deadline_auto_expires_active_task():
    expired = task(status="in_progress", deadline=datetime.utcnow() - timedelta(seconds=1))

    changed = expire_if_deadline_passed(expired)

    assert changed is True
    assert expired.status == "expired"
    assert expired.updated_at is not None


def test_deadline_does_not_change_terminal_task():
    completed = task(status="completed", deadline=datetime.utcnow() - timedelta(seconds=1))

    changed = expire_if_deadline_passed(completed)

    assert changed is False
    assert completed.status == "completed"
