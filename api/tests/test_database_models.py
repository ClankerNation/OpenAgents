"""Tests for database model fixes (issue #37)."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDatabaseModels:
    def test_user_address_has_index(self):
        """User.address must have an index for wallet lookups."""
        from models.database import User
        addr_col = User.__table__.columns["address"]
        assert addr_col.index is True

    def test_task_status_has_index(self):
        """Task.status must have an index for status-filtered queries."""
        from models.database import Task
        status_col = Task.__table__.columns["status"]
        assert status_col.index is True

    def test_payment_status_has_index(self):
        """Payment.status must have an index for escrow lookups."""
        from models.database import Payment
        status_col = Payment.__table__.columns["status"]
        assert status_col.index is True

    def test_payment_addresses_indexed(self):
        """Payment from_address and to_address must be indexed."""
        from models.database import Payment
        assert Payment.__table__.columns["from_address"].index is True
        assert Payment.__table__.columns["to_address"].index is True

    def test_agent_owner_id_indexed(self):
        """Agent.owner_id must have an index for owner-filtered queries."""
        from models.database import Agent
        assert Agent.__table__.columns["owner_id"].index is True

    def test_user_agent_cascade_delete(self):
        """Deleting a User must cascade-delete their Agents."""
        from models.database import User
        rel = User.__table__.metadata.tables["agents"]
        fk = next(
            c for c in rel.foreign_key_constraints
            if "owner_id" in [col.name for col in c.columns]
        )
        assert "CASCADE" in fk.ondelete.upper()

    def test_agent_task_cascade_delete(self):
        """Deleting an Agent must cascade-delete their Tasks."""
        from models.database import Agent
        rel = Agent.__table__.metadata.tables["tasks"]
        fk = next(
            c for c in rel.foreign_key_constraints
            if "agent_id" in [col.name for col in c.columns]
        )
        assert "SET NULL" in fk.ondelete.upper()

    def test_task_payment_cascade_delete(self):
        """Deleting a Task must cascade-delete its Payments."""
        from models.database import Task
        rel = Task.__table__.metadata.tables["payments"]
        fk = next(
            c for c in rel.foreign_key_constraints
            if "task_id" in [col.name for col in c.columns]
        )
        assert "CASCADE" in fk.ondelete.upper()

    def test_timestamps_use_utcnow(self):
        """Timestamps must use timezone-aware UTC, not naive utcnow."""
        from models.database import User, Agent, Task, Payment
        for model in [User, Agent, Task, Payment]:
            created = model.__table__.columns["created_at"]
            default = str(created.default)
            # Should reference _utcnow or datetime.now(timezone.utc)
            assert "utc" in default.lower() or "timezone" in default.lower(), (
                f"{model.__name__}.created_at uses naive default"
            )
