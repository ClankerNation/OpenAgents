# @contributor Antigravity
# @platform You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding. You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question. The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is. This information may or may not be relevant to the coding task, it is up for you to decide.
# @runtime OS: macOS, Architecture: arm64, Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents, Shell: /bin/zsh
# @date 2026-05-30T19:32:03+07:00

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from api.models.database import Base, get_db, AuditLog, User
from api.middleware.auth import generate_login_tokens

# Test setup
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

def test_auth_protection():
    # Attempting to post config or users without credentials
    res = client.post("/admin/config", json={"key": "test", "value": "val"})
    assert res.status_code == 401
    
    # Attempting with non-admin credentials
    non_admin = generate_login_tokens(user_id="2", address="0xUser", roles=["user"])
    headers = {"Authorization": f"Bearer {non_admin['token']}"}
    res = client.post("/admin/config", json={"key": "test", "value": "val"}, headers=headers)
    assert res.status_code == 403

def test_log_creation_on_config_update():
    admin = generate_login_tokens(user_id="1", address="0xAdmin", roles=["admin"])
    headers = {"Authorization": f"Bearer {admin['token']}"}
    
    res = client.post("/admin/config", json={"key": "maintenance_mode", "value": "true"}, headers=headers)
    assert res.status_code == 200
    
    # Query database directly to verify log creation
    db = TestingSessionLocal()
    logs = db.query(AuditLog).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.action == "update_config"
    assert log.actor == "0xAdmin"
    assert log.target == "config:maintenance_mode"
    assert log.before_value == {"key": "maintenance_mode", "value": "false"}
    assert log.after_value == {"key": "maintenance_mode", "value": "true"}
    assert log.ip == "testclient"

def test_log_creation_on_user_creation_and_update():
    admin = generate_login_tokens(user_id="1", address="0xAdmin", roles=["admin"])
    headers = {"Authorization": f"Bearer {admin['token']}"}
    
    # Create user
    res = client.post("/admin/users", json={"address": "0xNewUser", "username": "bob"}, headers=headers)
    assert res.status_code == 200
    
    # Update user
    res = client.post("/admin/users", json={"address": "0xNewUser", "username": "bobby"}, headers=headers)
    assert res.status_code == 200
    
    db = TestingSessionLocal()
    logs = db.query(AuditLog).order_by(AuditLog.id).all()
    assert len(logs) == 2
    
    # First is creation
    assert logs[0].action == "create_user"
    assert logs[0].before_value is None
    assert logs[0].after_value["username"] == "bob"
    
    # Second is update
    assert logs[1].action == "update_user"
    assert logs[1].before_value["username"] == "bob"
    assert logs[1].after_value["username"] == "bobby"

def test_query_filtering_and_pagination():
    admin = generate_login_tokens(user_id="1", address="0xAdmin", roles=["admin"])
    headers = {"Authorization": f"Bearer {admin['token']}"}
    
    # Seed some logs directly in the DB with different timestamps and actions
    db = TestingSessionLocal()
    t1 = datetime.utcnow() - timedelta(days=2)
    t2 = datetime.utcnow() - timedelta(days=1)
    t3 = datetime.utcnow()
    
    l1 = AuditLog(action="create_user", actor="0xAdmin1", target="user:1", timestamp=t1)
    l2 = AuditLog(action="update_config", actor="0xAdmin2", target="config:x", timestamp=t2)
    l3 = AuditLog(action="update_config", actor="0xAdmin1", target="config:y", timestamp=t3)
    db.add_all([l1, l2, l3])
    db.commit()
    
    # Test filtering by actor
    res = client.get("/admin/audit-log?actor=0xAdmin1", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert {log["action"] for log in data["logs"]} == {"create_user", "update_config"}
    
    # Test filtering by action
    res = client.get("/admin/audit-log?action=update_config", headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] == 2
    
    # Test filtering by date range
    start = (datetime.utcnow() - timedelta(days=1, hours=12)).isoformat()
    end = (datetime.utcnow() - timedelta(hours=12)).isoformat()
    res = client.get(f"/admin/audit-log?start_date={start}&end_date={end}", headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["logs"][0]["actor"] == "0xAdmin2"
    
    # Test pagination
    res = client.get("/admin/audit-log?skip=1&limit=1", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["logs"]) == 1
    assert data["logs"][0]["actor"] == "0xAdmin2" # Reverse chronological order: l3(0xAdmin1), l2(0xAdmin2), l1(0xAdmin1)

def test_immutability():
    db = TestingSessionLocal()
    log = AuditLog(action="test", actor="0xAdmin", target="test", before_value=None, after_value=None)
    db.add(log)
    db.commit()
    
    # Try updating
    with pytest.raises(ValueError, match="immutable"):
        log.action = "modified"
        db.commit()
        
    db.rollback()
    
    # Try deleting
    with pytest.raises(ValueError, match="immutable"):
        db.delete(log)
        db.commit()
