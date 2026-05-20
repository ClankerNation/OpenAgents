from datetime import timedelta
import time

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from api.models.database import Agent, Base, Payment, Task, User


def _session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session(), engine


def _assert_utc(value):
    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)


def test_lookup_and_status_indexes_are_created():
    session, engine = _session()
    try:
        inspector = inspect(engine)
        indexes = {
            table: {
                column
                for index in inspector.get_indexes(table)
                for column in index["column_names"]
            }
            for table in ("users", "agents", "tasks", "payments")
        }

        assert "address" in indexes["users"]
        assert "owner_id" in indexes["agents"]
        assert "status" in indexes["tasks"]
        assert "creator_id" in indexes["tasks"]
        assert "agent_id" in indexes["tasks"]
        assert "status" in indexes["payments"]
        assert "task_id" in indexes["payments"]
        assert "from_address" in indexes["payments"]
        assert "to_address" in indexes["payments"]
    finally:
        session.close()
        engine.dispose()


def test_database_user_delete_cascades_agents_tasks_and_payments():
    session, engine = _session()
    try:
        user = User(address="0x1111111111111111111111111111111111111111")
        agent = Agent(name="CascadeBot", owner=user)
        task = Task(
            title="Cascade task",
            description="created by user and assigned to owned agent",
            reward_amount=10.0,
            status="open",
            creator=user,
            agent=agent,
        )
        payment = Payment(
            task=task,
            from_address=user.address,
            amount=10.0,
            status="escrowed",
        )
        session.add_all([user, agent, task, payment])
        session.commit()

        session.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": user.id},
        )
        session.commit()

        assert session.query(User).count() == 0
        assert session.query(Agent).count() == 0
        assert session.query(Task).count() == 0
        assert session.query(Payment).count() == 0
    finally:
        session.close()
        engine.dispose()


def test_orm_user_delete_cascades_owned_agents():
    session, engine = _session()
    try:
        user = User(address="0x2222222222222222222222222222222222222222")
        agent = Agent(name="OwnedBot", owner=user)
        session.add_all([user, agent])
        session.commit()

        session.delete(user)
        session.commit()

        assert session.query(User).count() == 0
        assert session.query(Agent).count() == 0
    finally:
        session.close()
        engine.dispose()


def test_agent_delete_nulls_task_assignment_without_deleting_task():
    session, engine = _session()
    try:
        owner = User(address="0x3333333333333333333333333333333333333333")
        creator = User(address="0x4444444444444444444444444444444444444444")
        agent = Agent(name="NullableBot", owner=owner)
        task = Task(
            title="Keep task",
            description="agent assignment should be optional",
            reward_amount=5.0,
            status="assigned",
            creator=creator,
            agent=agent,
        )
        session.add_all([owner, creator, agent, task])
        session.commit()

        session.execute(
            text("DELETE FROM agents WHERE id = :id"),
            {"id": agent.id},
        )
        session.commit()
        session.refresh(task)

        assert session.query(Task).count() == 1
        assert task.agent_id is None
    finally:
        session.close()
        engine.dispose()


def test_timestamp_values_roundtrip_as_utc_aware_datetimes():
    session, engine = _session()
    try:
        user = User(address="0x5555555555555555555555555555555555555555")
        agent = Agent(name="TimeBot", owner=user)
        task = Task(
            title="UTC task",
            description="timestamps should keep UTC tzinfo",
            reward_amount=15.0,
            status="open",
            creator=user,
            agent=agent,
        )
        payment = Payment(
            task=task,
            from_address=user.address,
            amount=15.0,
            status="escrowed",
        )
        session.add_all([user, agent, task, payment])
        session.commit()
        session.refresh(user)
        session.refresh(agent)
        session.refresh(task)
        session.refresh(payment)

        _assert_utc(user.created_at)
        _assert_utc(agent.created_at)
        _assert_utc(agent.updated_at)
        _assert_utc(task.created_at)
        _assert_utc(task.updated_at)
        _assert_utc(payment.created_at)
    finally:
        session.close()
        engine.dispose()


def test_task_updated_at_auto_updates_on_change():
    session, engine = _session()
    try:
        user = User(address="0x6666666666666666666666666666666666666666")
        task = Task(
            title="Auto update",
            description="updated_at should move on mutation",
            reward_amount=20.0,
            status="open",
            creator=user,
        )
        session.add_all([user, task])
        session.commit()
        session.refresh(task)
        original_updated_at = task.updated_at

        time.sleep(0.01)
        task.status = "review"
        session.commit()
        session.refresh(task)

        _assert_utc(task.updated_at)
        assert task.updated_at > original_updated_at
    finally:
        session.close()
        engine.dispose()


def test_agent_updated_at_auto_updates_on_change():
    session, engine = _session()
    try:
        user = User(address="0x7777777777777777777777777777777777777777")
        agent = Agent(name="UpdateBot", owner=user)
        session.add_all([user, agent])
        session.commit()
        session.refresh(agent)
        original_updated_at = agent.updated_at

        time.sleep(0.01)
        agent.description = "new description"
        session.commit()
        session.refresh(agent)

        _assert_utc(agent.updated_at)
        assert agent.updated_at > original_updated_at
    finally:
        session.close()
        engine.dispose()
