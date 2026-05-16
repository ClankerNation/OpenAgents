"""Tests for agent endpoint URL validation with SSRF protection.

Covers bounty #187 requirements:
- Valid public URLs accepted
- Invalid URL formats rejected
- Private/internal IPs rejected (SSRF protection)
- Unreachable URLs rejected
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock

from api.models.database import Base, get_db, Agent, User
from api.routes.agents import router as agents_router
from api.middleware.auth import get_current_user, create_access_token

# ---------------------------------------------------------------------------
# In-memory SQLite test DB
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create a test user in the DB and return a fake get_current_user that uses it
@pytest.fixture
def test_user():
    """Create a test user in the in-memory DB, return its data dict."""
    db = TestSessionLocal()
    user = User(address="0xTestUserAddress123456789012345678901234", username="tester")
    db.add(user)
    db.commit()
    db.refresh(user)
    user_data = {"id": str(user.id), "address": user.address, "roles": []}
    db.close()
    return user_data


# Build test app
test_app = FastAPI()
test_app.include_router(agents_router)
test_app.dependency_overrides[get_db] = override_get_db

client = TestClient(test_app)


@pytest.fixture(autouse=True)
def setup_db():
    """Recreate tables before each test."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_headers(test_user):
    """JWT auth headers for the given test user."""
    token = create_access_token({"sub": test_user["id"], "address": test_user["address"], "roles": []})
    return {"Authorization": f"Bearer {token}"}


def _mock_public_resolve(hostname):
    """Simulate getaddrinfo for a public host (example.com → 93.184.216.34)."""
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


def _mock_private_resolve(ip_str):
    """Simulate getaddrinfo resolving to a private IP."""
    return [(2, 1, 6, "", (ip_str, 0))]


def _mock_head_ok(*args, **kwargs):
    """Simulate a successful HEAD response (HTTP 200)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    return mock_resp


def _mock_head_timeout(*args, **kwargs):
    """Simulate a HEAD request that times out."""
    import httpx
    raise httpx.TimeoutException("timed out", request=MagicMock())


def _mock_head_connect_error(*args, **kwargs):
    """Simulate a HEAD request that cannot connect."""
    import httpx
    raise httpx.ConnectError("connection refused")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateAgentValidUrl:
    """Acceptance: valid public URL passes validation and is stored."""

    @patch("api.routes.agents.httpx.Client.head", side_effect=_mock_head_ok)
    @patch("api.routes.agents.socket.getaddrinfo", side_effect=_mock_public_resolve)
    def test_create_agent_valid_url(self, mock_resolve, mock_head, test_user):
        # Override auth dependency for this test
        test_app.dependency_overrides[get_current_user] = lambda: test_user

        payload = {
            "name": "Test Agent",
            "description": "A valid agent",
            "model_type": "gpt-4",
            "endpoint": "https://example.com/api",
        }
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == "Test Agent"
        assert data["endpoint"] == "https://example.com/api"


class TestCreateAgentInvalidUrlFormat:
    """Reject malformed or missing-scheme URLs."""

    def test_no_scheme_rejected(self, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        payload = {"name": "Bad", "endpoint": "example.com/api"}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 422, resp.text

    def test_ftp_scheme_rejected(self, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        payload = {"name": "Bad", "endpoint": "ftp://example.com/api"}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 422, resp.text

    def test_empty_string_treated_as_none(self, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        payload = {"name": "No Endpoint", "endpoint": ""}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        # Empty string is converted to None => allowed, no endpoint set
        assert resp.status_code == 200, resp.text
        assert resp.json()["endpoint"] is None


class TestCreateAgentPrivateIpRejected:
    """SSRF: private / internal IP addresses must be rejected."""

    @patch("api.routes.agents.socket.getaddrinfo")
    def test_localhost_127_0_0_1_rejected(self, mock_resolve, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        mock_resolve.side_effect = lambda h, _: _mock_private_resolve("127.0.0.1")
        payload = {"name": "SSRF", "endpoint": "http://127.0.0.1/admin"}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 422, resp.text

    @patch("api.routes.agents.socket.getaddrinfo")
    def test_private_10_0_0_1_rejected(self, mock_resolve, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        mock_resolve.side_effect = lambda h, _: _mock_private_resolve("10.0.0.1")
        payload = {"name": "SSRF", "endpoint": "http://10.0.0.1/"}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 422, resp.text

    @patch("api.routes.agents.socket.getaddrinfo")
    def test_private_192_168_1_1_rejected(self, mock_resolve, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        mock_resolve.side_effect = lambda h, _: _mock_private_resolve("192.168.1.1")
        payload = {"name": "SSRF", "endpoint": "https://192.168.1.1/"}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 422, resp.text

    @patch("api.routes.agents.socket.getaddrinfo")
    def test_private_172_16_0_1_rejected(self, mock_resolve, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        mock_resolve.side_effect = lambda h, _: _mock_private_resolve("172.16.0.1")
        payload = {"name": "SSRF", "endpoint": "http://172.16.0.1/"}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 422, resp.text


class TestCreateAgentUnreachableUrl:
    """Unreachable endpoints must be rejected."""

    @patch("api.routes.agents.socket.getaddrinfo", side_effect=_mock_public_resolve)
    @patch("api.routes.agents.httpx.Client.head", side_effect=_mock_head_timeout)
    def test_timeout_rejected(self, mock_head, mock_resolve, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        payload = {"name": "Timeout", "endpoint": "https://slow.example.com/"}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 422, resp.text

    @patch("api.routes.agents.socket.getaddrinfo", side_effect=_mock_public_resolve)
    @patch("api.routes.agents.httpx.Client.head", side_effect=_mock_head_connect_error)
    def test_connect_error_rejected(self, mock_head, mock_resolve, test_user):
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        payload = {"name": "Down", "endpoint": "https://down.example.com/"}
        resp = client.post("/agents/", json=payload, headers=_auth_headers(test_user))
        assert resp.status_code == 422, resp.text
