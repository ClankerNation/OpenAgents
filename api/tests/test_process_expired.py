"""Tests for auto-refunding expired escrows (Issue #197)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
import jwt
import os

os.environ["JWT_SECRET"] = "test_secret_long_enough_for_sha256_hashing"

from api.main import app
from api.models.database import Base, get_db, Payment, Task, User
from api.models.audit_log import AuditLog

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_expired.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def _get_admin_token():
    payload = {
        "sub": "1",
        "address": "0xCreatorAddress",
        "roles": ["admin"],
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")

def _setup_escrow(days_ago: int, status: str = "escrowed"):
    db = TestingSessionLocal()
    
    user = User(id=1, address="0xCreatorAddress", username="creator")
    db.add(user)
    db.commit()
    
    task = Task(
        id=100,
        title="Test Task",
        description="Test",
        reward_amount=10.0,
        status="open",
        creator_id=1,
        created_at=datetime.now(timezone.utc) - timedelta(days=60)
    )
    db.add(task)
    db.commit()
    
    payment = Payment(
        task_id=100,
        from_address="0xCreatorAddress",
        amount=10.0,
        status=status,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago)
    )
    db.add(payment)
    db.commit()
    db.close()

def test_fresh_escrow_not_refunded():
    _setup_escrow(days_ago=10)
    token = _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.post("/payments/process-expired", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["refunded_count"] == 0

def test_expired_escrow_is_refunded():
    _setup_escrow(days_ago=31)
    token = _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.post("/payments/process-expired", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["refunded_count"] == 1
    assert data["refunds"][0]["refunded_to"] == "0xCreatorAddress"
    
    # Verify DB state
    db = TestingSessionLocal()
    payment = db.query(Payment).filter(Payment.task_id == 100).first()
    assert payment.status == "refunded"
    assert payment.to_address == "0xCreatorAddress"
    
    # Verify audit log
    audit = db.query(AuditLog).filter(AuditLog.action == "escrow.auto_refund").first()
    assert audit is not None
    assert audit.target == f"payment:{payment.id}"
    db.close()

def test_already_claimed_not_refunded():
    _setup_escrow(days_ago=40, status="claimed")
    token = _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.post("/payments/process-expired", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["refunded_count"] == 0
