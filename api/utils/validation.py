"""
URL validation utilities for the OpenAgents API.

Provides robust endpoint URL validation including:
- Scheme enforcement (http/https only)
- Malformed URL detection
- Private/reserved IP blocking (including DNS-resolved private IPs)
- Localhost/loopback blocking
"""

import re
import socket
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

from pydantic import field_validator


# Private and reserved IPv4 networks
_PRIVATE_IPV4_NETWORKS = [
    ip_network("0.0.0.0/8"),         # Current network
    ip_network("10.0.0.0/8"),        # Private
    ip_network("127.0.0.0/8"),       # Loopback
    ip_network("169.254.0.0/16"),    # Link-local
    ip_network("172.16.0.0/12"),     # Private
    ip_network("192.0.0.0/24"),      # IETF Protocol Assignments
    ip_network("192.0.2.0/24"),      # TEST-NET-1
    ip_network("192.88.99.0/24"),    # 6to4 Relay Anycast
    ip_network("192.168.0.0/16"),    # Private
    ip_network("198.18.0.0/15"),     # Network Interconnect
    ip_network("198.51.100.0/24"),   # TEST-NET-2
    ip_network("203.0.113.0/24"),    # TEST-NET-3
    ip_network("224.0.0.0/4"),       # Multicast
    ip_network("240.0.0.0/4"),       # Reserved
    ip_network("255.255.255.255/32"),# Limited broadcast
]

# Private IPv6 networks
_PRIVATE_IPV6_NETWORKS = [
    ip_network("::1/128"),            # Loopback
    ip_network("::/0"),               # Default route / unspecified — treat as invalid
    ip_network("fc00::/7"),           # Unique local
    ip_network("fe80::/10"),          # Link-local
    ip_network("ff00::/8"),           # Multicast
]


def _is_private_ip(host: str) -> bool:
    """Check if a hostname resolves to a private/reserved IP address.

    Handles both direct IP addresses and DNS-resolved hostnames.
    """
    # Try direct IP parsing first
    try:
        addr = ip_address(host)
        # Check IPv4 private networks
        for net in _PRIVATE_IPV4_NETWORKS:
            if addr.version == 4 and addr in net:
                return True
        # Check IPv6 private networks
        for net in _PRIVATE_IPV6_NETWORKS:
            if addr.version == 6 and addr in net:
                return True
        return False
    except ValueError:
        pass

    # Hostname — resolve it
    try:
        addrs = socket.getaddrinfo(host, None)
        for addr_info in addrs:
            ip_str = addr_info[4][0]
            try:
                addr = ip_address(ip_str)
                for net in _PRIVATE_IPV4_NETWORKS:
                    if addr.version == 4 and addr in net:
                        return True
                for net in _PRIVATE_IPV6_NETWORKS:
                    if addr.version == 6 and addr in net:
                        return True
            except ValueError:
                continue
        return False
    except (socket.gaierror, OSError):
        # Can't resolve — not necessarily private, let through
        return False


def validate_endpoint_url(url: str) -> str:
    """Validate an agent endpoint URL.

    Rules:
    - Must be a valid URL format
    - Scheme must be http or https
    - Host must not be a private/reserved IP address
    - Host must not be localhost/loopback
    - Must not contain fragments or unsupported schemes

    Returns the validated URL on success.
    Raises ValueError with a descriptive message on failure.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Endpoint URL is required and must be a string")

    # Strip whitespace
    url = url.strip()

    if not url:
        raise ValueError("Endpoint URL must not be empty")

    # Basic URL parsing
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Malformed endpoint URL: {e}")

    # Scheme validation
    if not parsed.scheme:
        raise ValueError("Endpoint URL must include a scheme (http:// or https://)")
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Endpoint URL scheme must be http or https, got '{parsed.scheme}'")

    # Host validation
    if not parsed.netloc:
        raise ValueError("Endpoint URL must include a hostname or IP address")

    host = parsed.hostname
    if not host:
        raise ValueError("Endpoint URL must include a valid hostname or IP address")

    # Block localhost/loopback
    localhost_patterns = (
        "localhost",
        "127.0.0.1",
        "127.0.1.1",
        "::1",
        "0.0.0.0",
        "[::1]",
    )
    if host.lower() in localhost_patterns:
        raise ValueError("Endpoint URL must not point to localhost or loopback address")

    # Block common local hostnames
    if host.lower().startswith("127.") and host.split(".")[0] == "127":
        raise ValueError("Endpoint URL must not point to a loopback address (127.x.x.x)")

    # Block private/reserved IPs via DNS resolution
    if _is_private_ip(host):
        raise ValueError("Endpoint URL must not point to a private or reserved IP address")

    # Block URLs with fragments
    if parsed.fragment:
        raise ValueError("Endpoint URL must not contain a fragment (#)")

    # Block URLs with credentials in the URL
    if parsed.username or parsed.password:
        raise ValueError("Endpoint URL must not contain embedded credentials")

    # Reconstruct clean URL
    clean_url = f"{parsed.scheme}://{host}"
    if parsed.port:
        clean_url += f":{parsed.port}"
    clean_url += parsed.path.rstrip("/") or "/"

    return clean_url


# Pydantic field validator for use in Pydantic models
def endpoint_url_validator(cls, v: str) -> str:
    """Pydantic v2 field validator wrapper for endpoint URL."""
    return validate_endpoint_url(v)
