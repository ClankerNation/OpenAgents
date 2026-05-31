import logging
import os
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.models.database import Base, Payment, Task, get_db
from api.routes import payments as payments_routes


@pytest.fixture
def client_and_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = testing_session_local()
    app = FastAPI()
    app.include_router(payments_routes.router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, db
    finally:
        client.close()
        db.close()


def create_task(db, task_id: int):
    task = Task(
        id=task_id,
        title=f"Task {task_id}",
        description="Escrow test task",
        reward_amount=100.0,
        status="open",
        creator_id=1,
        created_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    return task


def test_process_expired_leaves_fresh_escrow_untouched(client_and_db):
    client, db = client_and_db
    create_task(db, task_id=1)

    fresh_payment = Payment(
        task_id=1,
        from_address="0x1111111111111111111111111111111111111111",
        amount=5.0,
        status="escrowed",
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    db.add(fresh_payment)
    db.commit()
    db.refresh(fresh_payment)

    assert fresh_payment.expired_at == fresh_payment.created_at + timedelta(days=30)

    response = client.post("/payments/process-expired")
    assert response.status_code == 200
    assert response.json()["processed"] == 0

    db.refresh(fresh_payment)
    assert fresh_payment.status == "escrowed"
    assert fresh_payment.to_address is None
    assert fresh_payment.claimed_at is None


def test_process_expired_refunds_all_expired_and_logs(client_and_db, caplog):
    client, db = client_and_db
    create_task(db, task_id=2)

    expired_a = Payment(
        task_id=2,
        from_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount=7.0,
        status="escrowed",
        created_at=datetime.utcnow() - timedelta(days=31),
    )
    expired_b = Payment(
        task_id=2,
        from_address="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount=9.0,
        status="escrowed",
        created_at=datetime.utcnow() - timedelta(days=45),
    )
    fresh = Payment(
        task_id=2,
        from_address="0xcccccccccccccccccccccccccccccccccccccccc",
        amount=3.0,
        status="escrowed",
        created_at=datetime.utcnow() - timedelta(days=5),
    )
    db.add_all([expired_a, expired_b, fresh])
    db.commit()
    db.refresh(expired_a)
    db.refresh(expired_b)
    db.refresh(fresh)

    caplog.set_level(logging.INFO, logger=payments_routes.__name__)
    response = client.post("/payments/process-expired")
    assert response.status_code == 200
    payload = response.json()
    assert payload["processed"] == 2
    assert set(payload["refunded_escrow_ids"]) == {expired_a.id, expired_b.id}

    db.refresh(expired_a)
    db.refresh(expired_b)
    db.refresh(fresh)

    assert expired_a.status == "refunded"
    assert expired_a.to_address == expired_a.from_address
    assert expired_a.claimed_at is not None

    assert expired_b.status == "refunded"
    assert expired_b.to_address == expired_b.from_address
    assert expired_b.claimed_at is not None

    assert fresh.status == "escrowed"
    assert fresh.to_address is None

    log_output = " ".join(caplog.messages)
    assert f"escrow_id={expired_a.id}" in log_output
    assert f"escrow_id={expired_b.id}" in log_output
    assert "timestamp=" in log_output
