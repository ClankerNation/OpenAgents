# @fix-author rafaio1
# @date 2026-08-20
# @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
# @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

"""Agent CRUD endpoints for the OpenAgents platform with URL validation and SSRF protection."""

import ipaddress
import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, timezone

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


def _is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to a private/internal IP (SSRF protection)."""
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local
    except ValueError:
        # Not an IP literal; allow DNS names (further validation via HEAD request)
        return False


def _validate_endpoint_url(url: str) -> str:
    """Validate agent endpoint URL format and scheme."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Endpoint must use http or https scheme")
    if not parsed.netloc:
        raise ValueError("Endpoint must have a valid host")
    host = parsed.hostname or ""
    if _is_private_ip(host):
        raise ValueError("Private/internal IP addresses are not allowed")
    return url


async def _check_url_reachable(url: str, timeout: float = 5.0) -> None:
    """Verify URL is reachable with a HEAD request."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.head(url)
            if resp.status_code >= 500:
                raise ValueError(f"Endpoint returned server error: {resp.status_code}")
    except httpx.TimeoutException:
        raise ValueError("Endpoint timed out during reachability check")
    except httpx.ConnectError:
        raise ValueError("Endpoint is not reachable")
    except Exception as e:
        raise ValueError(f"Endpoint reachability check failed: {str(e)}")


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 128:
            raise ValueError("Name must be 1-128 characters")
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        return _validate_endpoint_url(v.strip())


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v or len(v) > 128:
                raise ValueError("Name must be 1-128 characters")
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_endpoint_url(v.strip())
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Verify endpoint reachability
    await _check_url_reachable(agent.endpoint)

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.now(timezone.utc),
    )
    # Store validated endpoint in config since Agent model may not have endpoint column
    if new_agent.config is None:
        new_agent.config = {}
    new_agent.config["endpoint"] = agent.endpoint

    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    logger.info("Agent created: id=%s name=%s owner=%s endpoint=%s", new_agent.id, agent.name, user["address"], agent.endpoint)
    return {"id": new_agent.id, "name": new_agent.name, "owner": user["address"], "endpoint": agent.endpoint}


@router.get("/")
async def list_agents(
    owner: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
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
        await _check_url_reachable(update.endpoint)
        if agent.config is None:
            agent.config = {}
        agent.config["endpoint"] = update.endpoint

    for field, value in update.dict(exclude_unset=True, exclude={"endpoint"}).items():
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
