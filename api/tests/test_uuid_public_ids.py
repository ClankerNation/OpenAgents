"""UUID public ID regression tests.

@contributor codex-gpt5
@platform Codex Desktop session bootstrap (platform-managed initialization context)
@runtime Windows 11 x64, cwd=F:/jiedan/OpenAgents
@date 2026-05-31T03:41:14Z
"""

import os
import tempfile
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.models import database as db_models
from api.models.database import User, Agent, Task, Payment
from api.routes.agents import router as agents_router
from api.routes.tasks import router as tasks_router
from api.routes.payments import router as payments_router


def _assert_uuid4(value: str) -> None:
    parsed = UUID(value)
    assert parsed.version == 4


@pytest.fixture()
def test_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_models.Base.metadata.create_all(bind=engine)

    try:
        yield session_local
    finally:
        db_models.Base.metadata.drop_all(bind=engine)
        engine.dispose()
        os.remove(db_path)


@pytest.fixture()
def client(test_db):
    app = FastAPI()
    app.include_router(agents_router)
    app.include_router(tasks_router)
    app.include_router(payments_router)

    def override_get_db():
        db = test_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_models.get_db] = override_get_db
    return TestClient(app)


def _seed_records(test_db):
    db = test_db()
    try:
        user = User(address="0x1111111111111111111111111111111111111111", username="u1")
        db.add(user)
        db.flush()

        agent = Agent(name="agent-1", owner_id=user.id)
        db.add(agent)
        db.flush()

        task = Task(
            title="task-1",
            description="desc",
            reward_amount=1.5,
            creator_id=user.id,
            agent_id=agent.id,
            status="open",
        )
        db.add(task)
        db.flush()

        payment = Payment(
            task_id=task.id,
            from_address=user.address,
            amount=2.5,
            status="escrowed",
        )
        db.add(payment)
        db.commit()
        db.refresh(user)
        db.refresh(agent)
        db.refresh(task)
        db.refresh(payment)
        return user, agent, task, payment
    finally:
        db.close()


def test_models_generate_uuid_v4(test_db):
    user, agent, task, payment = _seed_records(test_db)
    _assert_uuid4(user.uuid)
    _assert_uuid4(agent.uuid)
    _assert_uuid4(task.uuid)
    _assert_uuid4(payment.uuid)


def test_api_returns_public_uuid_and_no_internal_integer_ids(client, test_db):
    _, agent, task, _ = _seed_records(test_db)

    agent_resp = client.get(f"/agents/{agent.uuid}")
    assert agent_resp.status_code == 200
    agent_data = agent_resp.json()
    assert agent_data["id"] == agent.uuid
    _assert_uuid4(agent_data["id"])
    assert "owner_id" not in agent_data

    task_resp = client.get(f"/tasks/{task.uuid}")
    assert task_resp.status_code == 200
    task_data = task_resp.json()
    assert task_data["id"] == task.uuid
    _assert_uuid4(task_data["id"])
    assert "creator_id" not in task_data


def test_payment_escrow_uses_task_uuid_in_response(client, test_db):
    _, _, task, _ = _seed_records(test_db)

    escrow_resp = client.get(f"/payments/escrow/{task.uuid}")
    assert escrow_resp.status_code == 200
    payload = escrow_resp.json()
    assert payload["task_id"] == task.uuid
    _assert_uuid4(payload["task_id"])
