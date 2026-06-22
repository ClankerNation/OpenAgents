"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import re
import socket
import httpx

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


def _is_private_ip(host: str) -> bool:
    """Check if host is a private/internal IP address."""
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return False
    # 10.x.x.x
    if octets[0] == 10:
        return True
    # 172.16-31.x.x
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return True
    # 192.168.x.x
    if octets[0] == 192 and octets[1] == 168:
        return True
    # 127.x.x.x (localhost)
    if octets[0] == 127:
        return True
    # ::1 (IPv6 localhost)
    if ip == "::1":
        return True
    return False


def _validate_url(url: str) -> bool:
    """Validate URL format: must be valid http/https URL."""
    pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+'  # domain
        r'[A-Z]{2,63}'  # TLD
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    return bool(pattern.match(url))


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: Optional[str] = None  # Agent endpoint URL for reachability


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Validate endpoint URL if provided
    if agent.endpoint:
        if not _validate_url(agent.endpoint):
            raise HTTPException(status_code=400, detail="Invalid endpoint URL format: must be valid http/https URL")
        # Check for private/internal IPs (SSRF protection)
        try:
            from urllib.parse import urlparse
            parsed = urlparse(agent.endpoint)
            hostname = parsed.hostname or parsed.netloc
            if _is_private_ip(hostname):
                raise HTTPException(status_code=400, detail="Endpoint must not point to a private/internal IP address")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid endpoint URL: could not resolve hostname")

        # Verify reachability with HEAD request (timeout 5s)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(agent.endpoint, follow_redirects=False)
                if resp.status_code >= 400:
                    raise HTTPException(status_code=400, detail=f"Endpoint not reachable: HTTP {resp.status_code}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=400, detail="Endpoint not reachable: request timed out after 5s")
        except httpx.ConnectError:
            raise HTTPException(status_code=400, detail="Endpoint not reachable: connection refused")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Endpoint validation failed: {str(e)}")

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
async def delete_agent(agent_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Not the owner")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
