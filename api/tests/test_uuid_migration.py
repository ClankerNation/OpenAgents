# Test suite for UUID primary key migration
import pytest
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from ..models.database import User, Agent, Task, Payment, Base, engine, SessionLocal


@pytest.fixture
def db_session():
    """Create a clean in-memory database for testing."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
    Base.metadata.drop_all(bind=engine)


class TestUUIDGeneration:

    def test_user_has_uuid_on_create(self, db_session):
        user = User(address="0x1234567890123456789012345678901234567890")
        db_session.add(user)
        db_session.commit()
        assert user.uuid is not None
        assert len(user.uuid) == 36  # UUID v4 format
        # Verify valid UUID
        uuid.UUID(user.uuid)

    def test_agent_has_uuid_on_create(self, db_session):
        user = User(address="0x1234567890123456789012345678901234567890")
        db_session.add(user)
        db_session.commit()
        agent = Agent(name="TestAgent", owner_id=user.id)
        db_session.add(agent)
        db_session.commit()
        assert agent.uuid is not None
        assert len(agent.uuid) == 36
        uuid.UUID(agent.uuid)

    def test_task_has_uuid_on_create(self, db_session):
        user = User(address="0x1234567890123456789012345678901234567890")
        db_session.add(user)
        db_session.commit()
        task = Task(title="Test Task", reward_amount=100.0, creator_id=user.id)
        db_session.add(task)
        db_session.commit()
        assert task.uuid is not None
        uuid.UUID(task.uuid)

    def test_payment_has_uuid_on_create(self, db_session):
        user = User(address="0x1234567890123456789012345678901234567890")
        db_session.add(user)
        db_session.commit()
        task = Task(title="Test Task", reward_amount=100.0, creator_id=user.id)
        db_session.add(task)
        db_session.commit()
        payment = Payment(task_id=task.id, from_address=user.address, amount=50.0)
        db_session.add(payment)
        db_session.commit()
        assert payment.uuid is not None
        uuid.UUID(payment.uuid)

    def test_unique_uuids(self, db_session):
        """Ensure each instance gets a unique UUID."""
        user1 = User(address="0x1111111111111111111111111111111111111111")
        user2 = User(address="0x2222222222222222222222222222222222222222")
        db_session.add(user1)
        db_session.add(user2)
        db_session.commit()
        assert user1.uuid != user2.uuid

    def test_internal_id_still_exists(self, db_session):
        user = User(address="0x3333333333333333333333333333333333333333")
        db_session.add(user)
        db_session.commit()
        assert user.id is not None
        assert isinstance(user.id, int)
