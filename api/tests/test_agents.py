"""Tests for agent CRUD endpoint validation."""

from pydantic import BaseModel, field_validator, ValidationError
from typing import Optional
import pytest


class _AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    endpoint: str
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("endpoint must be a valid HTTP or HTTPS URL")
        return v


class _AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("endpoint must be a valid HTTP or HTTPS URL")
        return v


class TestAgentCreateValidation:
    def test_valid_agent(self):
        agent = _AgentCreate(name="My Agent", endpoint="https://api.example.com/agent")
        assert agent.name == "My Agent"
        assert agent.endpoint == "https://api.example.com/agent"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            _AgentCreate(name="", endpoint="https://example.com")

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError):
            _AgentCreate(name="   ", endpoint="https://example.com")

    def test_http_endpoint_accepted(self):
        agent = _AgentCreate(name="agent", endpoint="http://localhost:8080")
        assert agent.endpoint == "http://localhost:8080"

    def test_https_endpoint_accepted(self):
        agent = _AgentCreate(name="agent", endpoint="https://api.agent.com/v1")
        assert agent.endpoint == "https://api.agent.com/v1"

    def test_non_url_endpoint_rejected(self):
        with pytest.raises(ValidationError):
            _AgentCreate(name="agent", endpoint="not-a-url")

    def test_ftp_endpoint_rejected(self):
        with pytest.raises(ValidationError):
            _AgentCreate(name="agent", endpoint="ftp://files.example.com")


class TestAgentUpdateValidation:
    def test_valid_update(self):
        update = _AgentUpdate(name="New Name", endpoint="https://new.example.com")
        assert update.name == "New Name"

    def test_partial_update_name_only(self):
        update = _AgentUpdate(name="Just Name")
        assert update.name == "Just Name"
        assert update.endpoint is None

    def test_partial_update_endpoint_only(self):
        update = _AgentUpdate(endpoint="https://endpoint.only.com")
        assert update.endpoint == "https://endpoint.only.com"

    def test_update_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            _AgentUpdate(name="")

    def test_update_bad_endpoint_rejected(self):
        with pytest.raises(ValidationError):
            _AgentUpdate(endpoint="bad-url")
