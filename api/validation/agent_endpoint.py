"""Agent endpoint URL validation with SSRF protection."""

import asyncio
import ipaddress
import socket
from typing import Iterable
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException


ALLOWED_ENDPOINT_SCHEMES = {"http", "https"}
ENDPOINT_TIMEOUT_SECONDS = 5.0


def _is_blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def _validate_url_shape(endpoint: str):
    parsed = urlparse(endpoint)

    if parsed.scheme not in ALLOWED_ENDPOINT_SCHEMES:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint must be a valid http or https URL",
        )
    if not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint must include a hostname",
        )
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint must not include credentials",
        )

    try:
        if _is_blocked_ip(parsed.hostname):
            raise HTTPException(
                status_code=422,
                detail="Agent endpoint must not target private or internal IPs",
            )
    except ValueError:
        # Hostname is not an IP literal; DNS resolution is checked separately.
        pass

    return parsed


def _resolve_host(hostname: str) -> Iterable[str]:
    resolved = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    return {result[4][0] for result in resolved}


async def _resolved_addresses(hostname: str) -> Iterable[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _resolve_host, hostname)


async def validate_agent_endpoint(endpoint: str) -> str:
    """Validate that an agent endpoint is public, reachable, and safe to store."""

    parsed = _validate_url_shape(endpoint)

    try:
        addresses = await _resolved_addresses(parsed.hostname)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint hostname could not be resolved",
        ) from exc

    if not addresses:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint hostname could not be resolved",
        )

    if any(_is_blocked_ip(address) for address in addresses):
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint must not resolve to private or internal IPs",
        )

    try:
        async with httpx.AsyncClient(timeout=ENDPOINT_TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.head(endpoint)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Agent endpoint reachability check timed out",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=422,
            detail="Agent endpoint could not be reached with a HEAD request",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=422,
            detail=f"Agent endpoint HEAD check returned HTTP {response.status_code}",
        )

    return endpoint
