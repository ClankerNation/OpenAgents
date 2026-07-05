"""Agent management with endpoint URL validation."""
from fastapi import APIRouter, HTTPException
from urllib.parse import urlparse
import ipaddress, re

router = APIRouter(prefix="/agents", tags=["agents"])

URL_PATTERN = re.compile(r'^https?://[a-zA-Z0-9\-._~:/?#@!$&\'()*+,;=]+$')

def validate_endpoint_url(url: str) -> bool:
    """Validate agent endpoint URL with SSRF protection."""
    if not url or len(url) > 2048:
        return False
    if not URL_PATTERN.match(url):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    # SSRF: block private/loopback IPs
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            return False
    except ValueError:
        pass  # Domain name
    return True

@router.post("/")
async def create_agent(name: str, endpoint_url: str):
    if not validate_endpoint_url(endpoint_url):
        raise HTTPException(400, "Invalid endpoint URL")
    return {"name": name, "endpoint": endpoint_url, "status": "active"}

@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    raise HTTPException(404, "Agent not found")
