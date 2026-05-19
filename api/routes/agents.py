/**
 * @generated-by
 * name: oocheol
 * platform_instructions: Gemini CLI engineering agent. Focus: Non-destructive, idiomatic code modifications, comprehensive testing, and secure credential handling. Follows Research-Strategy-Execution lifecycle.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\PC","working_dir":"C:\\chromeMCP\\OpenAgents"}
 */
import re
import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# SSRF-blocked networks: private, loopback, link-local, CGNAT
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_private_ip(hostname: str) -> bool:
    """Resolve hostname and check if any IP belongs to a blocked network."""
    try:
        # Resolve all associated IPs
        addr_info = socket.getaddrinfo(hostname, None)
        for item in addr_info:
            ip = item[4][0]
            addr = ipaddress.ip_address(ip)
            for network in BLOCKED_NETWORKS:
                if addr in network:
                    return True
    except Exception:
        # If resolution fails, we'll let the reachability check handle it
        pass
    return False


def check_reachability(url: str, timeout: int = 5):
    """Verify URL is reachable with a HEAD request."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status >= 400:
                raise ValueError(f"Endpoint returned error status: {response.status}")
    except urllib.error.URLError as e:
        raise ValueError(f"Endpoint unreachable: {str(e)}")
    except socket.timeout:
        raise ValueError(f"Endpoint connection timed out after {timeout}s")
    except Exception as e:
        raise ValueError(f"Error checking endpoint reachability: {str(e)}")


def validate_endpoint_url(url: str) -> str:
    """Validate and sanitize an agent endpoint URL.
    
    Checks:
    - Valid http/https URL format
    - Reachability (HEAD request)
    - No private/internal IPs (SSRF protection with DNS resolution)
    - No credentials in URL
    
    Returns the normalized URL string.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Endpoint URL is required and must be a string")
    
    url = url.strip()
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError(f"Invalid URL format: {url[:100]}")
    
    # Must have scheme and netloc
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL must include scheme (http/https) and host: {url[:100]}")
    
    # Only http/https
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got: {parsed.scheme}")
    
    # No credentials in URL
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain credentials (username:password)")
    
    # Extract hostname for IP check
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL has no valid hostname: {url[:100]}")
    
    # SSRF protection: block private/internal IPs (includes DNS resolution)
    if is_private_ip(hostname):
        raise ValueError(f"URL points to a private/internal IP address: {hostname}")
    
    # Reject extremely long URLs
    if len(url) > 2048:
        raise ValueError(f"URL exceeds maximum length of 2048 characters")
    
    # Reachability check
    check_reachability(url)
    
    return url


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_valid_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                return validate_endpoint_url(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_valid_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                return validate_endpoint_url(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        endpoint=agent.endpoint,
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return {
        "id": new_agent.id,
        "name": new_agent.name,
        "endpoint": new_agent.endpoint,
        "owner": user["address"],
    }


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        query = query.filter(Agent.owner_id == owner)
    return query.offset(skip).limit(limit).all()


@router.get("/{agent_id}")
async def get_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int, update: AgentUpdate, user=Depends(get_current_user), db=Depends(get_db)
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
