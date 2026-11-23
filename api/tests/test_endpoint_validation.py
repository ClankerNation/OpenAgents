"""Tests for agent endpoint validation (Issue #139)."""

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, User, Agent
from validation import validate_endpoint_url, is_private_ip, PRIVATE_IP_RANGES

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

def test_is_private_ip_v4_private():
    assert is_private_ip("10.0.0.1") is True
    assert is_private_ip("172.16.0.1") is True
    assert is_private_ip("172.31.255.255") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("169.254.1.1") is True

def test_is_private_ip_v6_private():
    assert is_private_ip("::1") is True
    assert is_private_ip("fc00::1") is True
    assert is_private_ip("fe80::1") is True

def test_is_private_ip_public():
    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("1.1.1.1") is False
    assert is_private_ip("2001:4860:4860::8888") is False

def test_is_private_ip_hostname():
    assert is_private_ip("example.com") is False
    assert is_private_ip("google.com") is False

@pytest.mark.asyncio
async def test_validate_endpoint_valid_http():
    with patch("httpx.AsyncClient.head", new_callable=AsyncMock) as mock_head:
        mock_head.return_value = AsyncMock()
        result = await validate_endpoint_url("http://example.com/api")
        assert result == "http://example.com/api"

@pytest.mark.asyncio
async def test_validate_endpoint_valid_https():
    with patch("httpx.AsyncClient.head", new_callable=AsyncMock) as mock_head:
        mock_head.return_value = AsyncMock()
        result = await validate_endpoint_url("https://api.example.com/v1")
        assert result == "https://api.example.com/v1"

@pytest.mark.asyncio
async def test_validate_endpoint_invalid_scheme():
    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        await validate_endpoint_url("ftp://example.com")

@pytest.mark.asyncio
async def test_validate_endpoint_no_host():
    with pytest.raises(ValueError, match="valid host"):
        await validate_endpoint_url("http://")

@pytest.mark.asyncio
async def test_validate_endpoint_embedded_credentials():
    with pytest.raises(ValueError, match="embedded credentials"):
        await validate_endpoint_url("http://user:pass@example.com")

@pytest.mark.asyncio
async def test_validate_endpoint_private_ip_v4():
    with pytest.raises(ValueError, match="private/internal IP"):
        await validate_endpoint_url("http://10.0.0.1/api")

@pytest.mark.asyncio
async def test_validate_endpoint_localhost():
    with pytest.raises(ValueError, match="internal hostname"):
        await validate_endpoint_url("http://localhost:8080/api")

@pytest.mark.asyncio
async def test_validate_endpoint_timeout():
    with patch("httpx.AsyncClient.head", new_callable=AsyncMock) as mock_head:
        import httpx
        mock_head.side_effect = httpx.TimeoutException("timeout")
        with pytest.raises(ValueError, match="timed out"):
            await validate_endpoint_url("http://example.com/api")

@pytest.mark.asyncio
async def test_validate_endpoint_connection_error():
    with patch("httpx.AsyncClient.head", new_callable=AsyncMock) as mock_head:
        import httpx
        mock_head.side_effect = httpx.ConnectError("connection failed")
        with pytest.raises(ValueError, match="not reachable"):
            await validate_endpoint_url("http://example.com/api")

def test_agent_model_has_endpoint_field(db_session):
    user = User(address="0x1234567890123456789012345678901234567890", username="testuser")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    agent = Agent(name="Test Agent", owner_id=user.id, endpoint="https://example.com/api")
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    assert agent.endpoint == "https://example.com/api"

def test_agent_model_endpoint_nullable(db_session):
    user = User(address="0x1234567890123456789012345678901234567890", username="testuser")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    agent = Agent(name="Test Agent", owner_id=user.id)
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    assert agent.endpoint is None
