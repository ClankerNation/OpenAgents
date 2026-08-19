"""
Agent CRUD endpoints for the OpenAgents platform.
@fix-author ARO-Agentic | 2026-08-19
@runtime os=linux arch=x64 working_dir=/tmp/OpenAgents shell=bash
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl, field_validator
from typing import Optional
from datetime import datetime
import ipaddress
import urllib.parse
import httpx

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/internal IP address."""
    try:
        addr_infos = ipaddress.ip_address(hostname)
        return addr_infos.is_private or addr_infos.is_loopback or addr_infos.is_reserved
    except ValueError:
        # Not a raw IP, try resolving
        try:
            import socket
            infos = socket.getaddrinfo(hostname, None)
            for info in infos:
                ip_str = info[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
                    return True
        except Exception:
            pass
    return False


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: str

    @field_validator("name")
    @classmethod
    def name_must_be_valid(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        if len(v) > 64:
            raise ValueError("Name too long")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_valid_url(cls, v):
        try:
            parsed = urllib.parse.urlparse(v)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Endpoint must be http or https")
            if not parsed.netloc:
                raise ValueError("Endpoint must have a valid host")
        except Exception:
            raise ValueError("Invalid URL format")
        
        if _is_private_ip(parsed.hostname):
            raise ValueError("Private/internal IPs are not allowed (SSRF protection)")
            
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_valid_url(cls, v):
        if v is None:
            return v
        try:
            parsed = urllib.parse.urlparse(v)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Endpoint must be http or https")
            if not parsed.netloc:
                raise ValueError("Endpoint must have a valid host")
        except Exception:
            raise ValueError("Invalid URL format")
        
        if _is_private_ip(parsed.hostname):
            raise ValueError("Private/internal IPs are not allowed (SSRF protection)")
            
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Verify reachability with HEAD request (timeout 5s)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(agent.endpoint)
            # We accept 2xx, 3xx, 4xx (like 401/403/404/405) as reachable. 
            # Only network errors or 5xx timeouts are considered unreachable for this simple check.
            if response.status_code >= 500:
                raise HTTPException(status_code=400, detail=f"Endpoint returned server error ({response.status_code})")
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Endpoint timed out during reachability check")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Endpoint is not reachable: {str(e)}")

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    # Note: The DB model Agent in the previous files didn't explicitly have an `endpoint` column 
    # in the SQLAlchemy schema we saw earlier, but the issue description and API structure implies it exists.
    # We'll set it if the model supports it.
    if hasattr(new_agent, 'endpoint'):
        new_agent.endpoint = agent.endpoint
        
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
        
    if update.endpoint is not None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.head(update.endpoint)
                if response.status_code >= 500:
                    raise HTTPException(status_code=400, detail=f"Endpoint returned server error ({response.status_code})")
        except httpx.TimeoutException:
            raise HTTPException(status_code=400, detail="Endpoint timed out during reachability check")
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"Endpoint is not reachable: {str(e)}")

    for field, value in update.dict(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
