"""Tests for agent endpoint URL validation."""

import os
os.environ["JWT_SECRET"] = "test-secret-for-pytest"

import pytest
from ..routes.agents import AgentCreate


# --- Test: URL format validation ---

def test_valid_url():
    """Valid https URL should pass validation."""
    agent = AgentCreate(name="test", endpoint="https://httpbin.org/get", model_type="gpt-4")
    assert agent.endpoint.startswith("http")


def test_valid_http_url():
    """Valid http URL should pass validation."""
    agent = AgentCreate(name="test", endpoint="http://httpbin.org/get", model_type="gpt-4")
    assert agent.endpoint.startswith("http")


def test_invalid_scheme():
    """Invalid URL scheme should be rejected."""
    with pytest.raises(Exception):
        AgentCreate(name="test", endpoint="ftp://api.example.com", model_type="gpt-4")


def test_no_scheme():
    """URL without scheme should be rejected."""
    with pytest.raises(Exception):
        AgentCreate(name="test", endpoint="api.example.com", model_type="gpt-4")


# --- Test: SSRF protection ---

def test_private_ip_rejected():
    """Private IP range 10.x.x.x should be rejected."""
    with pytest.raises(Exception):
        AgentCreate(name="test", endpoint="http://10.0.0.1/api", model_type="gpt-4")


def test_loopback_rejected():
    """Loopback IP 127.0.0.1 should be rejected."""
    with pytest.raises(Exception):
        AgentCreate(name="test", endpoint="http://127.0.0.1:8080", model_type="gpt-4")


def test_localhost_rejected():
    """localhost hostname should be rejected."""
    with pytest.raises(Exception):
        AgentCreate(name="test", endpoint="http://localhost:8080/api", model_type="gpt-4")


def test_private_192_168_rejected():
    """Private IP range 192.168.x.x should be rejected."""
    with pytest.raises(Exception):
        AgentCreate(name="test", endpoint="http://192.168.1.1", model_type="gpt-4")


# --- Test: Reachability validation ---

def test_unreachable_url_fails():
    """Unreachable URL should fail validation."""
    with pytest.raises(Exception):
        AgentCreate(name="test", endpoint="https://this-domain-does-not-exist-12345.com", model_type="gpt-4")
