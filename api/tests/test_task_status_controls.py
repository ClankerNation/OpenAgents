import asyncio
import os
from datetime import datetime, timedelta

os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models.database import Base, Task, User
from api.routes.tasks import TaskStatusUpdate, list_tasks, update_task_status


def make_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed_task(db, *, creator_id=1, agent_id=2, status="in_progress", deadline=None):
    creator = User(id=creator_id, address=f"0x{creator_id:040d}")
    db.add(creator)
    if agent_id is not None:
        db.add(User(id=agent_id, address=f"0x{agent_id:040d}"))
    task = Task(
        title="task",
        reward_amount=1.0,
        status=status,
        creator_id=creator_id,
        agent_id=agent_id,
        deadline=deadline,
    )
    db.add(task)
    db.commit()
    return task


def assert_http_error(callable_, status_code, detail):
    try:
        callable_()
    except HTTPException as error:
        assert error.status_code == status_code
        assert error.detail == detail
    else:
        raise AssertionError("expected HTTPException")


def test_creator_cannot_complete_own_task():
    db = make_session()
    task = seed_task(db)

    assert_http_error(
        lambda: asyncio.run(update_task_status(
            task.id,
            TaskStatusUpdate(status="completed"),
            user={"id": 1, "address": "0x1"},
            db=db,
        )),
        403,
        "Creator cannot complete own task",
    )


def test_agent_can_complete_valid_transition():
    db = make_session()
    task = seed_task(db)

    result = asyncio.run(update_task_status(
        task.id,
        TaskStatusUpdate(status="completed"),
        user={"id": 2, "agent_id": 2, "address": "0x2"},
        db=db,
    ))

    assert result == {"id": task.id, "status": "completed"}


def test_invalid_transition_rejected():
    db = make_session()
    task = seed_task(db, status="open")

    assert_http_error(
        lambda: asyncio.run(update_task_status(
            task.id,
            TaskStatusUpdate(status="completed"),
            user={"id": 2, "agent_id": 2, "address": "0x2"},
            db=db,
        )),
        400,
        "Invalid status transition",
    )


def test_list_tasks_auto_expires_deadline_and_caps_limit():
    db = make_session()
    seed_task(db, status="open", deadline=datetime.utcnow() - timedelta(seconds=1))

    asyncio.run(list_tasks(skip=0, limit=100, db=db))

    assert db.query(Task).first().status == "cancelled"
