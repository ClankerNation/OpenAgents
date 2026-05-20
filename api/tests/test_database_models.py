from datetime import timezone
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from api.models.database import Agent, Base, Payment, Task, User, _utcnow


def _sqlite_session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _fk_ondelete(column, target):
    for foreign_key in column.foreign_keys:
        if foreign_key.target_fullname == target:
            return foreign_key.ondelete
    return None


def test_wallet_and_status_columns_are_indexed():
    assert User.__table__.c.address.index is True
    assert Task.__table__.c.status.index is True
    assert Payment.__table__.c.status.index is True


def test_foreign_keys_declare_safe_delete_behavior():
    assert _fk_ondelete(Agent.__table__.c.owner_id, "users.id") == "CASCADE"
    assert _fk_ondelete(Task.__table__.c.creator_id, "users.id") == "CASCADE"
    assert _fk_ondelete(Task.__table__.c.agent_id, "agents.id") == "SET NULL"
    assert _fk_ondelete(Payment.__table__.c.task_id, "tasks.id") == "CASCADE"


def test_user_agent_relationship_cascades_on_orm_delete():
    session = _sqlite_session()
    try:
        user = User(address="0x1111111111111111111111111111111111111111")
        agent = Agent(name="demo", owner=user)
        session.add(user)
        session.add(agent)
        session.commit()

        session.delete(user)
        session.commit()

        assert session.query(Agent).count() == 0
    finally:
        session.close()


def test_user_agent_relationship_cascades_at_database_level():
    session = _sqlite_session()
    try:
        user = User(address="0x2222222222222222222222222222222222222222")
        session.add(user)
        session.flush()
        session.add(Agent(name="db cascade", owner_id=user.id))
        session.commit()

        session.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": user.id},
        )
        session.commit()

        assert session.query(Agent).count() == 0
    finally:
        session.close()


def test_timestamp_columns_are_timezone_aware():
    now = _utcnow()

    assert now.tzinfo is timezone.utc
    assert User.__table__.c.created_at.type.timezone is True
    assert Agent.__table__.c.created_at.type.timezone is True
    assert Task.__table__.c.created_at.type.timezone is True
    assert Task.__table__.c.updated_at.type.timezone is True
    assert Task.__table__.c.updated_at.onupdate is not None
    assert Payment.__table__.c.created_at.type.timezone is True


def test_task_updated_at_auto_updates_on_change():
    session = _sqlite_session()
    try:
        user = User(address="0x3333333333333333333333333333333333333333")
        task = Task(title="demo", reward_amount=1.0, creator=user)
        session.add(task)
        session.commit()
        session.refresh(task)
        original_updated_at = task.updated_at

        time.sleep(0.01)
        task.status = "review"
        session.commit()
        session.refresh(task)

        assert task.updated_at > original_updated_at
    finally:
        session.close()
