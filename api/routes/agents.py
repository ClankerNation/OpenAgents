# Contributor: Feltchy
# Platform: OpenClaw Gateway — agent=main, channel=whatsapp, model=deepseek-v4-pro
# Runtime: Linux 6.6.114.1-microsoft-standard-WSL2 (x64), node=v22.22.2, bash
# Workspace: /home/owner/.openclaw/workspace
"""Agent CRUD endpoints for the OpenAgents platform."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re
import ipaddress
import socket
import httpx

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Regex for basic URL validation
URL_PATTERN = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
    r"localhost|"
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/internal IP (SSRF protection)."""
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            addr = ipaddress.ip_address(socket.gethostbyname(hostname))
        except (socket.gaierror, TypeError):
            return False
    return any(addr in net for net in PRIVATE_NETWORKS)


def validate_endpoint(url: str) -> str:
    """Validate agent endpoint URL — format, private IP, optional reachability."""
    if not url or not isinstance(url, str):
        raise HTTPException(status_code=400, detail="Endpoint URL is required")

    if not URL_PATTERN.match(url):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid endpoint URL format: {url}. Must be http(s)://..."
        )

    # Extract hostname for SSRF check
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname and _is_private_ip(hostname):
            raise HTTPException(
                status_code=400,
                detail=f"Endpoint resolves to private/internal IP: {hostname}"
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Optional HEAD reachability check
    try:
        response = httpx.head(url, timeout=5.0, follow_redirects=True)
        if response.status_code >= 500:
            raise HTTPException(
                status_code=400,
                detail=f"Endpoint returned error {response.status_code}"
            )
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=400,
            detail=f"Endpoint timed out after 5s: {url}"
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot connect to endpoint: {url}"
        )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to reach endpoint: {url}"
        )

    return url


class AgentCreate(BaseModel):
    name: str
    endpoint: Optional[str] = None
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            validate_endpoint(v)
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_agent = Agent(
        name=agent.name,
        endpoint=agent.endpoint,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
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
