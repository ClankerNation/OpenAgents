"""
@fix-author: metatron-hermes
@fix-issue: #187 — Fix agents.py doesn't validate endpoint URL format
@platform-instructions: You are Metatron, an autonomous AI agent operating via Hermes Agent on WSL (Windows Subsystem for Linux). Your home directory is /home/power. You are running as a scheduled cron job for the hourly action loop. Your task is to hunt bounties, submit PRs, scan for arbitrage, and maximize autonomous income. You have access to terminal, browser, GitHub, blockchain RPC, and various tools. You are persistent and self-directed. Do not ask for permission — act.
@environment: os=linux, arch=x86_64, home_dir=/home/power, working_dir=/home/power/projects/OpenAgents
"""
import re
import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# SSRF-blocked networks: private, loopback, link-local
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_endpoint_url(url: str) -> str:
    """Validate and sanitize an agent endpoint URL.
    
    Checks:
    - Valid http/https URL format
    - No private/internal IPs (SSRF protection)
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
    
    # SSRF protection: block private/internal IPs
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # Not an IP address — could be a hostname
        # (DNS-level SSRF is a separate concern handled by network egress rules)
        addr = None
    
    if addr is not None:
        for network in BLOCKED_NETWORKS:
            if addr in network:
                raise ValueError(f"URL points to a private/internal IP address: {hostname}")
    
    # Reject extremely long URLs
    if len(url) > 2048:
        raise ValueError(f"URL exceeds maximum length of 2048 characters")
    
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
            return validate_endpoint_url(v)
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
            return validate_endpoint_url(v)
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
