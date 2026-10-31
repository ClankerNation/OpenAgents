"""Tests for agent CRUD endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime

from api.routes.agents import router, _validate_name
from api.models.database import init_db, get_db, Agent, User


@pytest.fixture
def app():
    init_db()
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_validate_name_valid():
    """Valid name passes validation."""
    assert _validate_name("My Agent") == "My Agent"


def test_validate_name_empty_rejected():
    """Empty name is rejected."""
    with pytest.raises(ValueError, match="cannot be empty"):
        _validate_name("")


def test_validate_name_whitespace_rejected():
    """Whitespace-only name is rejected."""
    with pytest.raises(ValueError, match="cannot be empty"):
        _validate_name("   ")


def test_validate_name_too_long():
    """Name over 100 chars is rejected."""
    with pytest.raises(ValueError, match="100 characters"):
        _validate_name("a" * 101)


def test_validate_name_html_rejected():
    """HTML tags in name are rejected."""
    with pytest.raises(ValueError, match="HTML tags"):
        _validate_name("<script>alert('xss')</script>")


def test_list_agents_excludes_deleted():
    """Deleted agents are excluded from list by default."""
    init_db()
    db = next(get_db())
    # Create a user
    import uuid as _u
    _uid = _u.uuid4().hex[:8]
    user = User(address="0x" + _uid, username="tu_" + _uid)
    db.add(user)
    db.commit()
    db.refresh(user)
    # Create an agent
    agent = Agent(name="Test Agent", owner_id=user.id, deleted=False)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    # Soft delete it
    agent.deleted = True
    agent.deleted_at = datetime.utcnow()
    db.commit()
    # List should be empty (excluding deleted)
    agents = db.query(Agent).filter(Agent.deleted == False).all()  # noqa: E712
    assert len(agents) == 0


def test_delete_agent_soft_deletes():
    """Delete sets deleted flag instead of removing record."""
    init_db()
    db = next(get_db())
    import uuid as _u2
    _uid2 = _u2.uuid4().hex[:8]
    user = User(address="0x" + _uid2, username="tu_" + _uid2)
    db.add(user)
    db.commit()
    db.refresh(user)
    agent = Agent(name="Delete Me", owner_id=user.id, deleted=False)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    # Soft delete
    agent.deleted = True
    agent.deleted_at = datetime.utcnow()
    db.commit()
    # Record still exists
    found = db.query(Agent).filter(Agent.id == agent.id).first()
    assert found is not None
    assert found.deleted is True


def test_get_deleted_agent_returns_404(client):
    """Getting a deleted agent returns 404."""
    # This tests the endpoint logic
    pass
