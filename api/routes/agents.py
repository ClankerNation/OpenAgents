"""
Agent: Security Enhancement Agent
Timestamp: 2024-01-01T00:00:00Z
"""

"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse
import httpx
import ipaddress
import socket

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


class EndpointValidation(BaseModel):
    url: str


@router.post("/validate-endpoint")
async def validate_endpoint(endpoint: EndpointValidation):
    """Validate an endpoint URL with SSRF protection."""
    
    # Validate URL format
    try:
        parsed = urlparse(endpoint.url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(
                status_code=400,
                detail="Only HTTP and HTTPS URLs are allowed"
            )
        if not parsed.netloc:
            raise HTTPException(
                status_code=400,
                detail="Invalid URL format: missing hostname"
            )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid URL: {str(e)}"
        )
    
    # Resolve hostname to check for private IPs
    try:
        hostname = parsed.netloc.split(":")[0]
        ip_addresses = socket.getaddrinfo(hostname, None)
        
        for addr in ip_addresses:
            ip = ipaddress.ip_address(addr[4][0])
            
            # Check for private IP ranges
            if ip.is_private:
                raise HTTPException(
                    status_code=400,
                    detail="URL resolves to a private IP address (SSRF protection)"
                )
            if ip.is_loopback:
                raise HTTPException(
                    status_code=400,
                    detail="URL resolves to a loopback address (SSRF protection)"
                )
    except socket.gaierror:
        raise HTTPException(
            status_code=400,
            detail="Could not resolve hostname"
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid IP address resolution"
        )
    
    # HEAD reachability check with 5s timeout
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(endpoint.url, follow_redirects=True)
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail=f"Endpoint returned status code {response.status_code}"
                )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=400,
            detail="Endpoint connection timed out after 5 seconds"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not reach endpoint: {str(e)}"
        )
    
    return {
        "valid": True,
        "url": endpoint.url,
        "status_code": response.status_code
    }


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
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
    for field, value in update.dict(exclude_unset=True).items():
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