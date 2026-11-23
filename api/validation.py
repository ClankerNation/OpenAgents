"""URL validation utilities for agent endpoints."""

from urllib.parse import urlparse
import ipaddress
import httpx

PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

def is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in PRIVATE_IP_RANGES)
    except ValueError:
        return False

async def validate_endpoint_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Endpoint must use HTTP or HTTPS scheme")
    if not parsed.hostname:
        raise ValueError("Endpoint must have a valid host")
    if parsed.username or parsed.password:
        raise ValueError("Endpoint URL must not contain embedded credentials")
    if is_private_ip(parsed.hostname):
        raise ValueError("Endpoint host cannot be a private/internal IP address")
    internal_hostnames = {"localhost", "localhost.localdomain", "broadcasthost"}
    if parsed.hostname.lower() in internal_hostnames:
        raise ValueError("Endpoint host cannot be an internal hostname")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=5.0)) as client:
            await client.head(url, follow_redirects=True)
    except httpx.TimeoutException:
        raise ValueError("Endpoint HEAD request timed out after 5 seconds")
    except httpx.ConnectError:
        raise ValueError("Endpoint is not reachable (connection failed)")
    except httpx.RequestError as e:
        raise ValueError(f"Endpoint validation failed: {str(e)}")
    return url
