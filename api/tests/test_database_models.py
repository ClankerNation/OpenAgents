from datetime import datetime, timezone

from api.models.database import Agent, Payment, Task, User, utc_now


def test_wallet_and_status_columns_are_indexed():
    assert User.__table__.c.address.index is True
    assert Task.__table__.c.status.index is True
    assert Payment.__table__.c.status.index is True


def test_user_to_agent_cascade_is_configured():
    owner_id_fk = next(iter(Agent.__table__.c.owner_id.foreign_keys))

    assert owner_id_fk.ondelete == "CASCADE"
    assert "delete-orphan" in User.agents.property.cascade


def test_timestamps_are_timezone_aware():
    now = utc_now()

    assert isinstance(now, datetime)
    assert now.tzinfo is timezone.utc
    assert User.__table__.c.created_at.type.timezone is True
    assert Agent.__table__.c.created_at.type.timezone is True
    assert Task.__table__.c.created_at.type.timezone is True
    assert Payment.__table__.c.created_at.type.timezone is True


def test_updated_at_has_onupdate_hook():
    assert Agent.__table__.c.updated_at.onupdate is not None
    assert Task.__table__.c.updated_at.onupdate is not None
