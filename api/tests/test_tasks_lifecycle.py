import os
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.models.database import Agent, Base, Task, User  # noqa: E402
from api.routes import tasks as tasks_module  # noqa: E402


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
CURRENT_USER = {"id": "1", "address": "0xcreator"}


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


async def override_get_current_user():
    return CURRENT_USER


app = FastAPI()
app.include_router(tasks_module.router)
app.dependency_overrides[tasks_module.get_db] = override_get_db
app.dependency_overrides[
    tasks_module.get_current_user
] = override_get_current_user


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    return TestClient(app)


def add_user(db, user_id, address):
    user = User(id=user_id, address=address)
    db.add(user)
    return user


def add_task(db, *, creator_id=1, status="open", agent=None, deadline=None):
    task = Task(
        title=f"Task {status}",
        description="Lifecycle test task",
        reward_amount=10.0,
        status=status,
        creator_id=creator_id,
        agent=agent,
        created_at=datetime.utcnow(),
        deadline=deadline,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_creator_cannot_complete_with_string_token_subject(client, db_session):
    add_user(db_session, 1, "0xcreator")
    task = add_task(db_session, creator_id=1, status="review")

    CURRENT_USER.update({"id": "1", "address": "0xcreator"})
    response = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "completed"},
    )

    assert response.status_code == 403
    db_session.refresh(task)
    assert task.status == "review"


def test_assigned_agent_owner_can_complete_task(client, db_session):
    creator = add_user(db_session, 1, "0xcreator")
    worker = add_user(db_session, 2, "0xworker")
    agent = Agent(name="WorkerBot", owner=worker)
    db_session.add(agent)
    db_session.flush()
    task = add_task(
        db_session,
        creator_id=creator.id,
        status="assigned",
        agent=agent,
    )

    CURRENT_USER.update({"id": "2", "address": "0xworker"})
    response = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "completed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_invalid_status_and_transition_are_rejected(client, db_session):
    add_user(db_session, 1, "0xcreator")
    task = add_task(db_session, creator_id=1, status="open")
    CURRENT_USER.update({"id": "1", "address": "0xcreator"})

    invalid_status = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "done"},
    )
    invalid_transition = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "completed"},
    )

    assert invalid_status.status_code == 400
    assert invalid_transition.status_code == 400
    db_session.refresh(task)
    assert task.status == "open"


def test_list_tasks_caps_limit_at_100(client, db_session):
    add_user(db_session, 1, "0xcreator")
    for index in range(120):
        db_session.add(
            Task(
                title=f"Task {index}",
                description="Pagination test",
                reward_amount=1.0,
                status="open",
                creator_id=1,
                created_at=datetime.utcnow(),
            )
        )
    db_session.commit()

    response = client.get("/tasks/?limit=1000")

    assert response.status_code == 200
    assert len(response.json()) == 100


def test_overdue_tasks_are_expired_before_status_filtering(client, db_session):
    add_user(db_session, 1, "0xcreator")
    overdue = add_task(
        db_session,
        creator_id=1,
        status="open",
        deadline=datetime.utcnow() - timedelta(minutes=1),
    )
    add_task(
        db_session,
        creator_id=1,
        status="open",
        deadline=datetime.utcnow() + timedelta(days=1),
    )

    response = client.get("/tasks/?status=expired")

    assert response.status_code == 200
    expired_ids = {task["id"] for task in response.json()}
    assert overdue.id in expired_ids
    db_session.refresh(overdue)
    assert overdue.status == "expired"


def test_status_update_enforces_deadline_expiry(client, db_session):
    add_user(db_session, 1, "0xcreator")
    add_user(db_session, 2, "0xworker")
    task = add_task(
        db_session,
        creator_id=1,
        status="review",
        deadline=datetime.utcnow() - timedelta(seconds=1),
    )

    CURRENT_USER.update({"id": "2", "address": "0xworker"})
    response = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "completed"},
    )

    assert response.status_code == 400
    db_session.refresh(task)
    assert task.status == "expired"


def test_create_task_rejects_past_deadline(client, db_session):
    add_user(db_session, 1, "0xcreator")
    CURRENT_USER.update({"id": "1", "address": "0xcreator"})

    response = client.post(
        "/tasks/",
        json={
            "title": "Impossible deadline",
            "description": "Past deadlines should not be accepted",
            "reward_amount": 1.0,
            "deadline": (datetime.utcnow() - timedelta(seconds=1)).isoformat(),
        },
    )

    assert response.status_code == 400
