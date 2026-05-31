import asyncio
import ipaddress
import os
from typing import Dict, List

import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.routes import agents


def _public_resolver(hostname: str, port: int):
    return [ipaddress.ip_address("93.184.216.34")]


def _public_then_literal_resolver(hostname: str, port: int):
    try:
        return [ipaddress.ip_address(hostname)]
    except ValueError:
        return _public_resolver(hostname, port)


def _set_probe(monkeypatch, responses):
    calls = []
    response_iter = iter(responses)

    async def probe(target):
        calls.append(target)
        response = next(response_iter)
        if isinstance(response, Exception):
            raise response
        return agents.EndpointProbeResponse(
            status_code=response[0],
            headers=response[1] if len(response) > 1 else {},
        )

    monkeypatch.setattr(agents, "_request_endpoint_head", probe)
    return calls


def test_validate_agent_endpoint_accepts_reachable_public_url(monkeypatch):
    monkeypatch.setattr(agents, "_resolve_hostname_addresses", _public_resolver)
    calls = _set_probe(monkeypatch, [(200, {})])

    validated = asyncio.run(agents.validate_agent_endpoint(" https://example.com/agent "))

    assert validated == "https://example.com/agent"
    assert calls[0].url == "https://example.com/agent"
    assert calls[0].addresses == [ipaddress.ip_address("93.184.216.34")]


def test_validate_agent_endpoint_rejects_invalid_format():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint("not-a-url"))

    assert exc_info.value.status_code == 422
    assert "valid http/https URL" in exc_info.value.detail


@pytest.mark.parametrize(
    "url",
    [
        "http://10.1.2.3/agent",
        "http://192.168.1.5/agent",
        "http://127.0.0.1/agent",
        "http://[::1]/agent",
    ],
)
def test_validate_agent_endpoint_rejects_private_internal_ips(url):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint(url))

    assert exc_info.value.status_code == 422
    assert "private/internal IP" in exc_info.value.detail


def test_validate_agent_endpoint_rejects_timeout(monkeypatch):
    monkeypatch.setattr(agents, "_resolve_hostname_addresses", _public_resolver)
    calls = _set_probe(
        monkeypatch,
        [agents._validation_error("Agent endpoint reachability check timed out")],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint("https://example.com/agent"))

    assert exc_info.value.status_code == 422
    assert "timed out" in exc_info.value.detail
    assert calls[0].url == "https://example.com/agent"


def test_validate_agent_endpoint_accepts_head_method_not_allowed(monkeypatch):
    monkeypatch.setattr(agents, "_resolve_hostname_addresses", _public_resolver)
    calls = _set_probe(monkeypatch, [(405, {})])

    validated = asyncio.run(agents.validate_agent_endpoint("https://example.com/agent"))

    assert validated == "https://example.com/agent"
    assert calls[0].url == "https://example.com/agent"


def test_validate_agent_endpoint_blocks_private_redirect_before_following(monkeypatch):
    monkeypatch.setattr(agents, "_resolve_hostname_addresses", _public_then_literal_resolver)
    calls = _set_probe(monkeypatch, [(302, {"location": "http://127.0.0.1/agent"})])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint("https://example.com/agent"))

    assert exc_info.value.status_code == 422
    assert "private/internal IP" in exc_info.value.detail
    assert len(calls) == 1


def test_validate_agent_endpoint_rejects_redirect_without_location(monkeypatch):
    monkeypatch.setattr(agents, "_resolve_hostname_addresses", _public_resolver)
    _set_probe(monkeypatch, [(302, {})])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint("https://example.com/agent"))

    assert exc_info.value.status_code == 422
    assert "Location" in exc_info.value.detail


def test_validate_agent_endpoint_rejects_redirect_loop(monkeypatch):
    monkeypatch.setattr(agents, "_resolve_hostname_addresses", _public_resolver)
    calls = _set_probe(
        monkeypatch,
        [
            (302, {"location": "https://example.com/agent"}),
            (302, {"location": "https://example.com/agent"}),
            (302, {"location": "https://example.com/agent"}),
            (302, {"location": "https://example.com/agent"}),
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(agents.validate_agent_endpoint("https://example.com/agent"))

    assert exc_info.value.status_code == 422
    assert "too many redirects" in exc_info.value.detail
    assert len(calls) == agents.MAX_ENDPOINT_REDIRECTS + 1


def test_validate_agent_endpoint_uses_http_default_port(monkeypatch):
    ports = []

    def recording_resolver(hostname: str, port: int):
        ports.append(port)
        return _public_resolver(hostname, port)

    monkeypatch.setattr(agents, "_resolve_hostname_addresses", recording_resolver)
    _set_probe(monkeypatch, [(200, {})])

    asyncio.run(agents.validate_agent_endpoint("http://example.com/agent"))

    assert ports == [80]


class _FakeReader:
    async def readuntil(self, separator: bytes):
        return b"HTTP/1.1 204 No Content\r\nX-Test: yes\r\n\r\n"


class _FakeWriter:
    def __init__(self):
        self.data = b""
        self.closed = False
        self.waited = False

    def write(self, data: bytes):
        self.data += data

    async def drain(self):
        return None

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.waited = True


def test_request_endpoint_head_pins_request_to_validated_ip(monkeypatch):
    open_args: Dict[str, object] = {}
    writer = _FakeWriter()

    async def fake_open_connection(**kwargs):
        open_args.update(kwargs)
        return _FakeReader(), writer

    monkeypatch.setattr(agents.asyncio, "open_connection", fake_open_connection)
    target = agents.EndpointTarget(
        url="https://example.com/agent?case=1",
        parsed=agents.urlsplit("https://example.com/agent?case=1"),
        port=443,
        addresses=[ipaddress.ip_address("93.184.216.34")],
    )

    response = asyncio.run(agents._request_endpoint_head(target))

    assert response.status_code == 204
    assert response.headers["x-test"] == "yes"
    assert open_args["host"] == "93.184.216.34"
    assert open_args["port"] == 443
    assert open_args["server_hostname"] == "example.com"
    assert b"HEAD /agent?case=1 HTTP/1.1\r\n" in writer.data
    assert b"Host: example.com\r\n" in writer.data
    assert writer.closed is True
    assert writer.waited is True


def test_extract_agent_endpoint_accepts_existing_config_shape():
    endpoint = agents._extract_agent_endpoint(
        None,
        {"endpoint": "https://example.com/agent"},
        required=True,
    )

    assert endpoint == "https://example.com/agent"


def test_extract_agent_endpoint_rejects_conflicting_payload_shapes():
    with pytest.raises(HTTPException) as exc_info:
        agents._extract_agent_endpoint(
            "https://example.com/one",
            {"endpoint": "https://example.com/two"},
            required=True,
        )

    assert exc_info.value.status_code == 422
    assert "must match" in exc_info.value.detail


def test_merge_agent_config_preserves_endpoint_when_update_omits_it():
    merged = agents._merge_agent_config(
        {"endpoint": "https://example.com/agent", "model": "old"},
        {"model": "new"},
        None,
    )

    assert merged == {"endpoint": "https://example.com/agent", "model": "new"}
