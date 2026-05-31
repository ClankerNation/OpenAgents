import logging
import os
import uuid
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.models.database import Base, Payment, Task, User
from api.routes import payments


def _make_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(payments.router)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[payments.get_db] = override_get_db
    return TestClient(app), SessionLocal, engine


def _create_escrow(session, created_at: datetime):
    address = f"0x{uuid.uuid4().hex[:40]}"
    user = User(address=address, username=f"user-{uuid.uuid4().hex[:8]}")
    session.add(user)
    session.commit()
    session.refresh(user)

    task = Task(
        title="test task",
        description="task",
        reward_amount=1.0,
        status="open",
        creator_id=user.id,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    payment = Payment(
        task_id=task.id,
        from_address=address,
        amount=1.0,
        status="escrowed",
        created_at=created_at,
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment.id, address


def test_process_expired_fresh_escrow_not_affected():
    client, SessionLocal, engine = _make_client()
    try:
        session = SessionLocal()
        fresh_id, _ = _create_escrow(session, datetime.utcnow() - timedelta(days=5))
        session.close()

        response = client.post("/payments/process-expired")
        assert response.status_code == 200
        payload = response.json()
        assert payload["processed"] == 0
        assert payload["refunded_payment_ids"] == []

        verify = SessionLocal()
        fresh = verify.get(Payment, fresh_id)
        assert fresh.status == "escrowed"
        assert fresh.to_address is None
        verify.close()
    finally:
        client.close()
        engine.dispose()


def test_process_expired_refunds_expired_escrow_and_logs(caplog):
    client, SessionLocal, engine = _make_client()
    try:
        session = SessionLocal()
        expired_id, expired_from = _create_escrow(
            session, datetime.utcnow() - timedelta(days=31)
        )
        _create_escrow(session, datetime.utcnow() - timedelta(days=10))
        session.close()

        with caplog.at_level(logging.INFO, logger="api.routes.payments"):
            response = client.post("/payments/process-expired")

        assert response.status_code == 200
        payload = response.json()
        assert payload["processed"] == 1
        assert payload["refunded_payment_ids"] == [expired_id]

        verify = SessionLocal()
        expired = verify.get(Payment, expired_id)
        assert expired.status == "refunded"
        assert expired.to_address == expired_from
        assert expired.claimed_at is not None
        verify.close()

        assert f"id={expired_id}" in caplog.text
        assert "timestamp=" in caplog.text
    finally:
        client.close()
        engine.dispose()
