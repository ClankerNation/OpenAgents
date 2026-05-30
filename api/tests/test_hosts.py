"""Tests for the TrustedHostMiddleware — host header validation."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.hosts import (
    TrustedHostMiddleware,
    _strip_port,
    host_matches,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app(allowed_hosts: list[str]) -> TestClient:
    """Construct a minimal app with only the trusted-host middleware."""
    test_app = FastAPI()
    test_app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @test_app.get("/ping")
    async def ping():
        return {"pong": True}

    return TestClient(test_app)


# ---------------------------------------------------------------------------
# Unit tests — _strip_port helper
# ---------------------------------------------------------------------------

class TestStripPort:
    """Verify port-suffix removal across address formats."""

    def test_hostname_no_port(self):
        assert _strip_port("localhost") == "localhost"

    def test_hostname_with_port(self):
        assert _strip_port("localhost:8000") == "localhost"

    def test_ipv4_with_port(self):
        assert _strip_port("127.0.0.1:3000") == "127.0.0.1"

    def test_ipv4_no_port(self):
        assert _strip_port("127.0.0.1") == "127.0.0.1"

    def test_ipv6_bracketed_with_port(self):
        assert _strip_port("[::1]:8000") == "[::1]"

    def test_ipv6_bracketed_no_port(self):
        assert _strip_port("[::1]") == "[::1]"

    def test_domain_with_port(self):
        assert _strip_port("api.openagents.ai:443") == "api.openagents.ai"


# ---------------------------------------------------------------------------
# Unit tests — host_matches engine
# ---------------------------------------------------------------------------

class TestHostMatches:
    """Validate the wildcard-capable matching engine."""

    # Exact matches --------------------------------------------------------

    def test_exact_match(self):
        assert host_matches("localhost", ["localhost"]) is True

    def test_exact_match_case_insensitive(self):
        assert host_matches("LocalHost", ["localhost"]) is True

    def test_exact_match_with_port_stripped(self):
        assert host_matches("localhost:8000", ["localhost"]) is True

    def test_exact_ipv4(self):
        assert host_matches("127.0.0.1", ["127.0.0.1"]) is True

    def test_exact_ipv4_with_port(self):
        assert host_matches("127.0.0.1:3000", ["127.0.0.1"]) is True

    # Wildcard matches -----------------------------------------------------

    def test_wildcard_star(self):
        assert host_matches("anything.example.com", ["*"]) is True

    def test_wildcard_subdomain(self):
        assert host_matches("api.openagents.ai", ["*.openagents.ai"]) is True

    def test_wildcard_deep_subdomain(self):
        assert host_matches("v2.api.openagents.ai", ["*.openagents.ai"]) is True

    def test_wildcard_does_not_match_bare_domain(self):
        """``*.openagents.ai`` must NOT match ``openagents.ai`` itself."""
        assert host_matches("openagents.ai", ["*.openagents.ai"]) is False

    def test_wildcard_with_port(self):
        assert host_matches("api.openagents.ai:443", ["*.openagents.ai"]) is True

    # Rejections -----------------------------------------------------------

    def test_no_match(self):
        assert host_matches("evil.com", ["localhost", "127.0.0.1"]) is False

    def test_empty_host(self):
        assert host_matches("", ["localhost"]) is False

    def test_empty_allow_list(self):
        assert host_matches("localhost", []) is False

    def test_partial_name_no_match(self):
        """``malicious-localhost`` must not match ``localhost``."""
        assert host_matches("malicious-localhost", ["localhost"]) is False

    def test_subdomain_of_non_wildcard_no_match(self):
        """``sub.localhost`` must not match plain ``localhost``."""
        assert host_matches("sub.localhost", ["localhost"]) is False


# ---------------------------------------------------------------------------
# Integration tests — middleware HTTP responses
# ---------------------------------------------------------------------------

ALLOWED = ["localhost", "127.0.0.1", "*.openagents.ai"]


class TestTrustedHostMiddleware:
    """End-to-end tests through the full ASGI middleware stack."""

    # Allowed hosts --------------------------------------------------------

    def test_exact_host_allowed(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "localhost"})
        assert resp.status_code == 200
        assert resp.json() == {"pong": True}

    def test_ipv4_host_allowed(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "127.0.0.1"})
        assert resp.status_code == 200

    def test_wildcard_subdomain_allowed(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "api.openagents.ai"})
        assert resp.status_code == 200

    def test_deep_subdomain_allowed(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "v2.api.openagents.ai"})
        assert resp.status_code == 200

    def test_host_with_port_allowed(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "localhost:8000"})
        assert resp.status_code == 200

    def test_wildcard_host_with_port_allowed(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "api.openagents.ai:443"})
        assert resp.status_code == 200

    # Rejected hosts -------------------------------------------------------

    def test_unknown_host_rejected(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "evil.com"})
        assert resp.status_code == 400
        assert resp.text == "Invalid Host Header"

    def test_spoofed_subdomain_rejected(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "evil.openagents.ai.attacker.com"})
        assert resp.status_code == 400

    def test_bare_domain_with_wildcard_only_rejected(self):
        """When allow-list is only ``*.openagents.ai``, the bare domain fails."""
        client = _build_app(["*.openagents.ai"])
        resp = client.get("/ping", headers={"Host": "openagents.ai"})
        assert resp.status_code == 400

    def test_empty_host_header_rejected(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": ""})
        assert resp.status_code == 400

    def test_injection_newline_rejected(self):
        """Host headers containing injection characters must be blocked."""
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "localhost\r\nevil.com"})
        assert resp.status_code == 400

    def test_injection_null_byte_rejected(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "localhost\x00evil.com"})
        assert resp.status_code == 400

    # Global wildcard ------------------------------------------------------

    def test_global_wildcard_allows_anything(self):
        client = _build_app(["*"])
        resp = client.get("/ping", headers={"Host": "literally-anything.example"})
        assert resp.status_code == 200

    # Case insensitivity ---------------------------------------------------

    def test_case_insensitive_match(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "LOCALHOST"})
        assert resp.status_code == 200

    def test_case_insensitive_wildcard(self):
        client = _build_app(ALLOWED)
        resp = client.get("/ping", headers={"Host": "API.OpenAgents.AI"})
        assert resp.status_code == 200
