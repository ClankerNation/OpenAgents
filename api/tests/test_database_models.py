from datetime import timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models.database import Agent, Base, Payment, Task, User, _utcnow


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
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
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


def test_timestamps_are_timezone_aware_and_tasks_auto_update():
    now = _utcnow()

    assert now.tzinfo is timezone.utc
    assert User.__table__.c.created_at.type.timezone is True
    assert Agent.__table__.c.created_at.type.timezone is True
    assert Task.__table__.c.created_at.type.timezone is True
    assert Task.__table__.c.updated_at.type.timezone is True
    assert Task.__table__.c.updated_at.onupdate is not None
    assert Payment.__table__.c.created_at.type.timezone is True
