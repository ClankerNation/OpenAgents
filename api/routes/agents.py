"""Agent CRUD endpoints for the OpenAgents platform.
@generated-by: giren1011-lab
@timestamp: 2026-05-28T08:35:00Z
@purpose: Fix #139 - Validate agent endpoint URLs
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
import httpx
import re
from urllib.parse import urlparse

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Blocked IP ranges for SSRF protection
BLOCKED_NETWORKS = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "0.0.0.0/8",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
]

def is_private_ip(host: str) -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(host)
        return any(ipaddress.ip_address(host) in ipaddress.ip_network(net) for net in BLOCKED_NETWORKS)
    except ValueError:
        return False

def validate_agent_url(url: str) -> str:
    """Validate agent endpoint URL."""
    if not url or not isinstance(url, str):
        raise ValueError("URL is required")

    # Validate URL format
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must use http or https scheme")

    host = parsed.hostname or ""
    if not host:
        raise ValueError("URL must have a valid hostname")

    # Block private/internal IPs (SSRF protection)
    if is_private_ip(host):
        raise ValueError("URL must point to a public endpoint, not a private network")

    # Reject common internal hostnames
    internal_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}
    if host.lower() in internal_hosts:
        raise ValueError("URL must point to a public endpoint, not localhost")

    # Check reachability
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.head(url, follow_redirects=True)
            resp.raise_for_status()
    except httpx.TimeoutException:
        raise ValueError(f"Agent endpoint {url} timed out after 5 seconds")
    except httpx.RequestError as e:
        raise ValueError(f"Agent endpoint {url} is not reachable: {str(e)}")

    return url


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    endpoint: str

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Agent name cannot be empty")
        if len(v) > 100:
            raise ValueError("Agent name too long (max 100 chars)")
        if any(c in v for c in "<>"'&"):
            raise ValueError("Agent name contains invalid characters")
        return v.strip()

    @validator("endpoint")
    def validate_endpoint(cls, v):
        return validate_agent_url(v)


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None

    @validator("name")
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Agent name cannot be empty")
            if len(v) > 100:
                raise ValueError("Agent name too long (max 100 chars)")
            if any(c in v for c in "<>"'&"):
                raise ValueError("Agent name contains invalid characters")
        return v

    @validator("endpoint")
    def validate_endpoint(cls, v):
        if v is not None:
            return validate_agent_url(v)
        return v
