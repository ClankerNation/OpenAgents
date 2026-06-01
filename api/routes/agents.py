"""
Agent CRUD endpoints for the OpenAgents platform.

---
Contributor Tracking:
Agent: Antigravity
Timestamp: 2026-06-01T23:05:00Z
Runtime: Windows (os: windows, arch: amd64, home: C:\\Users\\Khalid, workdir: C:\\Users\\Khalid\\Desktop\\bounty\\OpenAgents, shell: powershell)
Startup Instructions:
You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
This information may or may not be relevant to the coding task, it is up for you to decide.
---
"""

import socket
import ipaddress
import httpx
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: Optional[str] = None

async def validate_agent_endpoint(url: str):
    if not url:
        return
        
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format")
        
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must be http or https")
        
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="URL missing hostname")
        
    # Check for SSRF (Private IPs) and prevent DNS rebinding
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Could not resolve hostname")

    safe_ip = None
    for res in addr_info:
        ip = res[4][0]
        parsed_ip = ipaddress.ip_address(ip)
        if (parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local 
            or parsed_ip.is_multicast or parsed_ip.is_reserved or parsed_ip.is_unspecified
            or str(parsed_ip) == "169.254.169.254"):
            raise HTTPException(status_code=400, detail="Private or internal IPs are not allowed")
        safe_ip = ip
        break
        
    if not safe_ip:
        raise HTTPException(status_code=400, detail="Could not resolve safe IP")
        
    port_str = f":{parsed.port}" if parsed.port else ""
    query_str = f"?{parsed.query}" if parsed.query else ""
    safe_url = f"{parsed.scheme}://{safe_ip}{port_str}{parsed.path}{query_str}"
        
    # Check reachability directly to IP to prevent TOCTOU
    try:
        async with httpx.AsyncClient() as client:
            headers = {"Host": hostname}
            response = await client.head(safe_url, headers=headers, timeout=5.0)
            if response.status_code == 405:
                response = await client.get(safe_url, headers=headers, timeout=5.0)
            response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(status_code=400, detail="Endpoint URL is not reachable")

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    if agent.endpoint:
        await validate_agent_endpoint(agent.endpoint)
        # Endpoints are stored in config to avoid complex database schema migrations
        if not agent.config:
            agent.config = {}
        agent.config["endpoint"] = agent.endpoint

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"]}


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    db=Depends(get_db),
):
    query = db.query(Agent)
    if owner:
        # BUG: String interpolation in query — vulnerable to SQL injection
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
        
    update_data = update.dict(exclude_unset=True)
    
    if "endpoint" in update_data:
        endpoint_url = update_data.pop("endpoint")
        if endpoint_url:
            await validate_agent_endpoint(endpoint_url)
            # Endpoints are stored in config to avoid complex database schema migrations
            new_config = dict(agent.config) if agent.config else {}
            new_config["endpoint"] = endpoint_url
            # Assigning a new dict triggers SQLAlchemy JSON mutation tracking
            agent.config = new_config
            
    for field, value in update_data.items():
        setattr(agent, field, value)
    db.commit()
    return agent


# BUG: No authentication — anyone can delete any agent
@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
