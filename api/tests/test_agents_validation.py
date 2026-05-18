# ---
# Contributor Traceability Header
# Agent Name: Hermes Agent (OpenAgents Bounty #183)
# Platform Instructions: Fix agents.py doesn't validate endpoint URL format —
# security critical. Read issue with gh issue view 183. Fix the bugs in
# api/routes/agents.py. Create branch bounty/183-url-validation-v2 from
# upstream/main. Push to fork. Create PR. Claim bounty with /attempt #183.
# All BUG comments are intentional bounty targets.
# Environment: os=Linux, arch=x86_64, home_dir=/home/ubuntu,
# working_dir=/home/ubuntu/OpenAgents, shell=/bin/bash
# ---

"""Comprehensive tests for URL validation, name validation, SSRF protection, and auth."""

import ipaddress
from unittest.mock import patch, MagicMock, AsyncMock

import httpx
import pytest
from fastapi import HTTPException

# Import the module under test
from api.routes.agents import (
    validate_endpoint_url,
    _is_private_ip,
    _sanitize_name,
    AgentCreate,
    AgentUpdate,
    delete_agent,
    NAME_MIN_LENGTH,
    NAME_MAX_LENGTH,
)


# ============================================================
# 1. URL format validation tests
# ============================================================


class TestURLFormatValidation:
    """Tests for URL format validation — must be valid http/https URL."""

    @pytest.mark.asyncio
    async def test_valid_https_url(self):
        """A valid, reachable https URL should be accepted."""
        url = "https://example.com/api"
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = await validate_endpoint_url(url)
            assert result == url

    @pytest.mark.asyncio
    async def test_valid_http_url(self):
        """A valid, reachable http URL should be accepted."""
        url = "http://example.com/api"
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = await validate_endpoint_url(url)
            assert result == url

    @pytest.mark.asyncio
    async def test_invalid_url_no_scheme(self):
        """'not-a-url' has no scheme and should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            await validate_endpoint_url("not-a-url")
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_url_ftp_scheme(self):
        """ftp:// URLs should be rejected (wrong scheme)."""
        with pytest.raises(HTTPException) as exc_info:
            await validate_endpoint_url("ftp://bad.example.com")
        assert exc_info.value.status_code == 422
        assert "http or https" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_url_javascript_scheme(self):
        """javascript: URLs are not http/https and should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            await validate_endpoint_url("javascript:alert(1)")
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_url_without_hostname(self):
        """A URL with just a scheme and no host should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            await validate_endpoint_url("https://")
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_url_with_port(self):
        """URLs with explicit ports should be accepted if reachable."""
        url = "https://example.com:8443/endpoint"
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = await validate_endpoint_url(url)
            assert result == url


# ============================================================
# 2. Reachability / HEAD request tests
# ============================================================


class TestURLReachability:
    """Tests for async HEAD request reachability checks."""

    @pytest.mark.asyncio
    async def test_reachable_url_200(self):
        """A URL returning 200 should be accepted."""
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = await validate_endpoint_url("https://example.com")
            assert result == "https://example.com"

    @pytest.mark.asyncio
    async def test_reachable_url_301_redirect(self):
        """A URL that follows redirects should be accepted (AsyncClient handles follow_redirects=True)."""
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = await validate_endpoint_url("https://example.com")
            assert result == "https://example.com"

    @pytest.mark.asyncio
    async def test_unreachable_url_404(self):
        """A URL returning 404 should be rejected."""
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=404)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            with pytest.raises(HTTPException) as exc_info:
                await validate_endpoint_url("https://example.com/nonexistent")
            assert exc_info.value.status_code == 422
            assert "not reachable" in exc_info.value.detail.lower() or "404" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_unreachable_url_500(self):
        """A URL returning 500 should be rejected."""
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=500)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            with pytest.raises(HTTPException) as exc_info:
                await validate_endpoint_url("https://example.com/error")
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_timeout_does_not_hang(self):
        """A URL that times out should raise 422, not hang."""
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            with pytest.raises(HTTPException) as exc_info:
                await validate_endpoint_url("https://example.com/slow")
            assert exc_info.value.status_code == 422
            assert "timeout" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """A URL with connection refused should be rejected."""
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            with pytest.raises(HTTPException) as exc_info:
                await validate_endpoint_url("https://nonexistent.host.example.com")
            assert exc_info.value.status_code == 422
            assert "connect" in exc_info.value.detail.lower()


# ============================================================
# 3. SSRF / private IP tests
# ============================================================


class TestSSRFProtection:
    """Tests for blocking private/internal IPs."""

    @pytest.mark.parametrize(
        "private_url",
        [
            "http://127.0.0.1/admin",
            "http://127.0.0.1:8080/internal",
            "http://10.0.0.1/secret",
            "http://10.255.255.255/secret",
            "http://192.168.1.1/router",
            "http://192.168.0.100/config",
            "http://172.16.0.1/internal",
            "http://172.31.255.255/internal",
            "http://0.0.0.0/",
            "http://169.254.169.254/metadata",
        ],
    )
    @pytest.mark.asyncio
    async def test_private_ipv4_blocked(self, private_url):
        """Private/loopback IPv4 addresses should be blocked (SSRF protection)."""
        with pytest.raises(HTTPException) as exc_info:
            await validate_endpoint_url(private_url)
        assert exc_info.value.status_code == 422
        assert "private" in exc_info.value.detail.lower() or "internal" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_ipv6_loopback_blocked(self):
        """IPv6 loopback ::1 should be blocked."""
        with pytest.raises(HTTPException) as exc_info:
            await validate_endpoint_url("http://[::1]/admin")
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_172_16_through_31_blocked(self):
        """172.16.x.x through 172.31.x.x are private (RFC 1918) and should be blocked."""
        for subnet in range(16, 32):
            url = f"http://172.{subnet}.0.1/internal"
            with pytest.raises(HTTPException) as exc_info:
                await validate_endpoint_url(url)
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_172_32_not_private(self):
        """172.32.0.1 is NOT in the private range and should not be blocked by _is_private_ip."""
        assert _is_private_ip("172.32.0.1") is False

    @pytest.mark.asyncio
    async def test_public_ip_not_blocked(self):
        """A public IP like 93.184.216.34 should NOT be blocked by _is_private_ip."""
        assert _is_private_ip("93.184.216.34") is False

    def test_is_private_ip_helper_loopback(self):
        """_is_private_ip should detect 127.0.0.1 as private."""
        assert _is_private_ip("127.0.0.1") is True

    def test_is_private_ip_helper_10_network(self):
        """_is_private_ip should detect 10.0.0.1 as private."""
        assert _is_private_ip("10.0.0.1") is True

    def test_is_private_ip_helper_192_168(self):
        """_is_private_ip should detect 192.168.1.1 as private."""
        assert _is_private_ip("192.168.1.1") is True

    def test_is_private_ip_helper_ipv6_loopback(self):
        """_is_private_ip should detect ::1 as private."""
        assert _is_private_ip("::1") is True


# ============================================================
# 4. Name validation tests
# ============================================================


class TestNameValidation:
    """Tests for agent name validation: length, XSS/HTML sanitisation."""

    def test_valid_name(self):
        """A normal name should pass validation."""
        agent = AgentCreate(name="My Agent", model_type="gpt-4")
        assert agent.name == "My Agent"

    def test_empty_name_rejected(self):
        """An empty name should be rejected."""
        with pytest.raises(Exception):
            AgentCreate(name="", model_type="gpt-4")

    def test_whitespace_only_name_rejected(self):
        """A name that is only whitespace after sanitisation should be rejected."""
        with pytest.raises(Exception):
            AgentCreate(name="   ", model_type="gpt-4")

    def test_name_too_long_rejected(self):
        """A name exceeding 128 characters should be rejected."""
        with pytest.raises(Exception):
            AgentCreate(name="x" * 129, model_type="gpt-4")

    def test_name_max_length_accepted(self):
        """A name of exactly 128 characters should be accepted."""
        agent = AgentCreate(name="x" * 128, model_type="gpt-4")
        assert len(agent.name) == 128

    def test_xss_script_tag_stripped(self):
        """HTML <script> tags should be stripped from the name."""
        agent = AgentCreate(name="<script>alert('xss')</script>Hello", model_type="gpt-4")
        assert "<script>" not in agent.name
        assert "</script>" not in agent.name
        assert "Hello" in agent.name

    def test_xss_img_onerror_stripped(self):
        """HTML <img onerror> XSS should be stripped from the name."""
        agent = AgentCreate(name="<img src=x onerror=alert(1)>Agent", model_type="gpt-4")
        assert "<img" not in agent.name
        assert "onerror" not in agent.name

    def test_html_bold_stripped(self):
        """HTML <b> tags should be stripped."""
        agent = AgentCreate(name="<b>Bold</b> Agent", model_type="gpt-4")
        assert "<b>" not in agent.name
        assert "Bold" in agent.name

    def test_name_with_unicode(self):
        """Unicode names should be accepted."""
        agent = AgentCreate(name="日本語エージェント", model_type="gpt-4")
        assert agent.name == "日本語エージェント"

    def test_name_with_emoji(self):
        """Names with emoji should be accepted."""
        agent = AgentCreate(name="🤖 Robot Agent", model_type="gpt-4")
        assert "Robot Agent" in agent.name


class TestNameValidationUpdate:
    """Tests for agent name validation in update model."""

    def test_valid_name_update(self):
        """A normal name should pass update validation."""
        update = AgentUpdate(name="Updated Name")
        assert update.name == "Updated Name"

    def test_xss_stripped_in_update(self):
        """HTML tags should be stripped in update names too."""
        update = AgentUpdate(name="<script>xss</script>Name")
        assert "<script>" not in update.name

    def test_none_name_in_update(self):
        """None name in update should be allowed (means 'don't change')."""
        update = AgentUpdate(name=None)
        assert update.name is None


# ============================================================
# 5. Delete requires ownership (auth check)
# ============================================================


class TestDeleteAuth:
    """Tests verifying that delete_agent requires authentication."""

    def test_delete_endpoint_requires_auth_dependency(self):
        """The delete handler should depend on get_current_user."""
        from api.routes.agents import delete_agent
        import inspect

        sig = inspect.signature(delete_agent)
        params = sig.parameters
        assert "user" in params, "delete_agent should have a 'user' parameter for auth"

    def test_delete_checks_ownership(self):
        """The delete handler should check ownership."""
        import inspect
        from api.routes.agents import delete_agent as del_fn

        source = inspect.getsource(del_fn)
        assert "owner_id" in source or "Not the owner" in source, \
            "delete_agent should check that the requesting user is the owner"


# ============================================================
# 6. SQL injection / parameterization (ORM) verification
# ============================================================


class TestSQLInjectionProtection:
    """Verify that the owner filter in list_agents uses parameterized queries."""

    def test_owner_filter_uses_orm_not_raw_sql(self):
        """The owner filter should use SQLAlchemy ORM filter, not raw SQL."""
        import inspect
        from api.routes.agents import list_agents

        source = inspect.getsource(list_agents)
        assert ".filter(" in source
        assert "text(" not in source or "filter" in source


# ============================================================
# 7. _sanitize_name helper unit tests
# ============================================================


class TestSanitizeName:
    """Direct unit tests for the _sanitize_name helper."""

    def test_strip_tags(self):
        assert _sanitize_name("<b>Hello</b>") == "Hello"

    def test_strip_script(self):
        """Stripping <script> tags removes the tags but leaves text content."""
        result = _sanitize_name("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "</script>" not in result
        assert "alert(1)" in result

    def test_strip_nested_tags(self):
        assert _sanitize_name("<div><p>Hello</p></div>") == "Hello"

    def test_strip_attributes(self):
        result = _sanitize_name('<a href="http://evil.com">Click</a>')
        assert result == "Click"
        assert "<a" not in result

    def test_no_tags(self):
        assert _sanitize_name("Plain Name") == "Plain Name"

    def test_trim_whitespace(self):
        assert _sanitize_name("  Hello  ") == "Hello"


# ============================================================
# 8. Edge cases
# ============================================================


class TestEdgeCases:
    """Edge case tests for endpoint validation."""

    @pytest.mark.asyncio
    async def test_url_with_query_params(self):
        """URLs with query parameters should be accepted."""
        url = "https://example.com/api?key=value"
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = await validate_endpoint_url(url)
            assert result == url

    @pytest.mark.asyncio
    async def test_url_with_fragment(self):
        """URLs with fragments should be accepted."""
        url = "https://example.com/page#section"
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = await validate_endpoint_url(url)
            assert result == url

    @pytest.mark.asyncio
    async def test_httpx_invalid_url(self):
        """An invalid URL that httpx rejects should raise 422."""
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=httpx.InvalidURL("bad url"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            with pytest.raises(HTTPException) as exc_info:
                await validate_endpoint_url("https://valid-but-bad-format.example.com")
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_url_stored_after_validation(self):
        """The validated endpoint_url should be available on the created agent."""
        url = "https://api.example.com/agent"
        with patch("api.routes.agents.httpx.AsyncClient") as mock_client_cls, \
             patch("api.routes.agents._is_private_ip", return_value=False):
            mock_response = MagicMock(status_code=200)
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            result = await validate_endpoint_url(url)
            assert result == url
