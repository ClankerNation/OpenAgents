"""Agent CRUD endpoints for the OpenAgents platform."""

import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
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

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate endpoint URL to prevent SSRF attacks.

        SSRF protection checks:
        - Only http/https protocols allowed
        - URL must be well-formed
        - Resolved IP must not be private/reserved/loopback/link-local
        """
        if v is None:
            return v

        parsed = urlparse(v)

        # Only allow http and https schemes
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"Endpoint URL must use http or https scheme, got '{parsed.scheme}'"
            )

        hostname = parsed.hostname
        if hostname is None:
            raise ValueError("Endpoint URL must contain a valid hostname")

        # Check if hostname is an IP address (direct IP = SSRF risk)
        try:
            ip = ipaddress.ip_address(hostname)
            if cls._is_private_ip(ip):
                raise ValueError(
                    f"Endpoint URL points to a private/reserved IP address ({hostname}), "
                    "which is blocked to prevent SSRF attacks"
                )
        except ValueError:
            # Hostname is a domain name, resolve it and check IPs
            import socket

            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for family, _, _, _, sockaddr in addr_info:
                    ip_str = sockaddr[0]
                    try:
                        ip_obj = ipaddress.ip_address(ip_str)
                        if cls._is_private_ip(ip_obj):
                            raise ValueError(
                                f"Endpoint URL resolves to a private/reserved IP address "
                                f"({ip_str}), which is blocked to prevent SSRF attacks"
                            )
                    except ValueError as e:
                        if "private/reserved" in str(e):
                            raise
            except socket.gaierror:
                raise ValueError(f"Could not resolve hostname '{hostname}'")

        return v

    @staticmethod
    def _is_private_ip(ip) -> bool:
        """Check if an IP address is private/reserved/loopback/link-local."""
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


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
