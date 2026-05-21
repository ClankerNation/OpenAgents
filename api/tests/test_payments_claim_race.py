import inspect
import os
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.models.database import Base, Payment, PaymentAuditLog, Task, User  # noqa: E402
from api.routes import payments as payments_module  # noqa: E402


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
app.include_router(payments_module.router)
app.dependency_overrides[payments_module.get_db] = override_get_db
app.dependency_overrides[
    payments_module.get_current_user
] = override_get_current_user


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    CURRENT_USER.update({"id": "1", "address": "0xcreator"})


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


def add_user(db, user_id=1, address="0xcreator"):
    user = User(id=user_id, address=address)
    db.add(user)
    db.commit()
    return user


def add_task(db, *, creator_id=1, status="completed"):
    task = Task(
        title="Payment task",
        description="Payment race-condition test task",
        reward_amount=100.0,
        status=status,
        creator_id=creator_id,
        created_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def add_payment(db, *, task_id, amount=10.0, status="escrowed"):
    payment = Payment(
        task_id=task_id,
        from_address="0xcreator",
        amount=amount,
        status=status,
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def audit_actions(db):
    return [entry.action for entry in db.query(PaymentAuditLog).all()]


def test_deposit_rejects_non_positive_amount(client, db_session):
    add_user(db_session)
    task = add_task(db_session, status="open")

    response = client.post(
        "/payments/escrow/deposit",
        json={"task_id": task.id, "amount": -1.0},
    )

    assert response.status_code == 422
    assert db_session.query(Payment).count() == 0


def test_deposit_idempotency_key_prevents_duplicate_escrow(client, db_session):
    add_user(db_session)
    task = add_task(db_session, status="open")

    first = client.post(
        "/payments/escrow/deposit",
        headers={"Idempotency-Key": "deposit-1"},
        json={"task_id": task.id, "amount": 25.0},
    )
    second = client.post(
        "/payments/escrow/deposit",
        headers={"Idempotency-Key": "deposit-1"},
        json={"task_id": task.id, "amount": 25.0},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["payment_id"] == second.json()["payment_id"]
    assert second.json()["idempotent"] is True
    assert db_session.query(Payment).count() == 1
    assert audit_actions(db_session) == ["deposit_created", "deposit_replayed"]


def test_claim_uses_row_lock_for_serialized_escrow_updates():
    source = inspect.getsource(payments_module.claim_payment)

    assert ".with_for_update()" in source


def test_claim_marks_all_escrow_claimed_and_logs_changes(client, db_session):
    add_user(db_session)
    task = add_task(db_session)
    first_payment = add_payment(db_session, task_id=task.id, amount=12.5)
    second_payment = add_payment(db_session, task_id=task.id, amount=7.5)

    response = client.post(
        "/payments/claim",
        headers={"Idempotency-Key": "claim-1"},
        json={"task_id": task.id, "recipient_address": "0xrecipient"},
    )

    assert response.status_code == 200
    assert response.json()["claimed_amount"] == 20.0
    db_session.refresh(first_payment)
    db_session.refresh(second_payment)
    assert first_payment.status == "claimed"
    assert second_payment.status == "claimed"
    assert first_payment.to_address == "0xrecipient"
    assert second_payment.claim_idempotency_key == "claim-1"
    assert audit_actions(db_session) == ["payment_claimed", "payment_claimed"]


def test_replayed_claim_is_idempotent(client, db_session):
    add_user(db_session)
    task = add_task(db_session)
    add_payment(db_session, task_id=task.id, amount=18.0)

    first = client.post(
        "/payments/claim",
        headers={"Idempotency-Key": "claim-repeat"},
        json={"task_id": task.id, "recipient_address": "0xrecipient"},
    )
    second = client.post(
        "/payments/claim",
        headers={"Idempotency-Key": "claim-repeat"},
        json={"task_id": task.id, "recipient_address": "0xrecipient"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["claimed_amount"] == first.json()["claimed_amount"]
    assert second.json()["idempotent"] is True
    assert db_session.query(Payment).filter(Payment.status == "claimed").count() == 1
    assert audit_actions(db_session) == ["payment_claimed", "claim_replayed"]


def test_second_claim_without_idempotency_key_cannot_double_claim(client, db_session):
    add_user(db_session)
    task = add_task(db_session)
    add_payment(db_session, task_id=task.id, amount=18.0)

    first = client.post(
        "/payments/claim",
        json={"task_id": task.id, "recipient_address": "0xrecipient"},
    )
    second = client.post(
        "/payments/claim",
        json={"task_id": task.id, "recipient_address": "0xrecipient"},
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["detail"] == "No escrowed funds available"


def test_claim_rejects_legacy_non_positive_escrow(client, db_session):
    add_user(db_session)
    task = add_task(db_session)
    payment = add_payment(db_session, task_id=task.id, amount=-5.0)

    response = client.post(
        "/payments/claim",
        headers={"Idempotency-Key": "claim-negative"},
        json={"task_id": task.id, "recipient_address": "0xrecipient"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Escrowed payment amount must be positive"
    db_session.refresh(payment)
    assert payment.status == "escrowed"
    assert audit_actions(db_session) == ["claim_rejected"]
