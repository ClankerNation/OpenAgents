"""Tests for UUID models (Issue #122)."""

import pytest
import uuid as uuid_lib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, User, Agent, Task, Payment

# Test database
TEST_DB_URL = "sqlite:///./test_openagents.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_user_model_has_uuid(db_session):
    """User model should have uuid field."""
    user = User(address="0x1234567890123456789012345678901234567890", username="testuser")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    assert user.uuid is not None
    assert len(user.uuid) == 36
    assert user.id is not None

def test_agent_model_has_uuid(db_session):
    """Agent model should have uuid field."""
    user = User(address="0x1234567890123456789012345678901234567890", username="testuser")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    agent = Agent(name="Test Agent", owner_id=user.id)
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    
    assert agent.uuid is not None
    assert len(agent.uuid) == 36
    assert agent.id is not None

def test_task_model_has_uuid(db_session):
    """Task model should have uuid field."""
    user = User(address="0x1234567890123456789012345678901234567890", username="testuser")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    task = Task(title="Test Task", description="Desc", reward_amount=100.0, creator_id=user.id)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    
    assert task.uuid is not None
    assert len(task.uuid) == 36
    assert task.id is not None

def test_payment_model_has_uuid(db_session):
    """Payment model should have uuid field."""
    user = User(address="0x1234567890123456789012345678901234567890", username="testuser")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    task = Task(title="Test Task", description="Desc", reward_amount=100.0, creator_id=user.id)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    
    payment = Payment(task_id=task.id, from_address=user.address, amount=50.0)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    
    assert payment.uuid is not None
    assert len(payment.uuid) == 36
    assert payment.id is not None

def test_uuids_are_unique(db_session):
    """All UUIDs should be unique across instances."""
    uuids = set()
    for i in range(10):
        addr = f"0x{i:040x}"
        user = User(address=addr, username=f"user{i}")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        assert user.uuid not in uuids
        uuids.add(user.uuid)
    
    assert len(uuids) == 10

def test_uuid_format_is_valid(db_session):
    """UUIDs should be valid UUID v4 format."""
    user = User(address="0x1234567890123456789012345678901234567890", username="testuser")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    parsed = uuid_lib.UUID(user.uuid)
    assert parsed.version == 4
