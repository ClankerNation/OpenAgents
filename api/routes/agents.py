"""Agent CRUD endpoints for the OpenAgents platform.

@fix-author Gaotax2006
@date 2026-06-25
@runtime os=win32 arch=amd64 working_dir=F:\\ai-bounty-work\\bounty-hunter\\OpenAgents-fork shell=bash
@fixes #173 — Add URL validation, HEAD request reachability check, SSRF protection
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re
import socket
import struct

import aiohttp
from aiohttp import ClientTimeout

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# Private/reserved IP ranges for SSRF protection
PRIVATE_IP_RANGES = [
    # 10.0.0.0/8
    (socket.inet_aton("10.0.0.0"), socket.inet_aton("255.0.0.0")),
    # 172.16.0.0/12
    (socket.inet_aton("172.16.0.0"), socket.inet_aton("255.240.0.0")),
    # 192.168.0.0/16
    (socket.inet_aton("192.168.0.0"), socket.inet_aton("255.255.0.0")),
    # 127.0.0.0/8 (loopback)
    (socket.inet_aton("127.0.0.0"), socket.inet_aton("255.0.0.0")),
    # 0.0.0.0
    (socket.inet_aton("0.0.0.0"), socket.inet_aton("255.255.255.255")),
    # ::1 (IPv6 loopback)
]

HTTP_TIMEOUT = ClientTimeout(total=5)


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address falls within private/reserved ranges."""
    try:
        packed = socket.inet_aton(ip_str)
        for network, mask in PRIVATE_IP_RANGES:
            # Simple mask-based check
            net_int = struct.unpack("!I", network)[0]
            mask_int = struct.unpack("!I", mask)[0]
            packed_int = struct.unpack("!I", packed)[0]
            if (packed_int & mask_int) == (net_int & mask_int):
                # Additional check: ensure it's not a public IP in the same major range
                if ip_str.startswith("10.") or ip_str.startswith("192.168.") or ip_str.startswith("172."):
                    return True
                if ip_str.startswith("127."):
                    return True
                if ip_str == "0.0.0.0":
                    return True
        return False
    except (socket.error, struct.error):
        return True  # Assume private if we can't parse


def _validate_url(url: str) -> bool:
    """Validate URL format and check for SSRF."""
    # Basic URL format check
    pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+'  # domain
        r'[a-zA-Z]{2,}'  # TLD
        r'(?::\d{1,5})?'  # optional port
        r'(?:/[^\s]*)?$'  # optional path
    )
    if not pattern.match(url):
        return False

    # Extract hostname and check for private IPs
    hostname = url.split("//")[1].split(":")[0].split("/")[0]

    # Check if hostname is an IP address
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', hostname):
        if _is_private_ip(hostname):
            return False

    # DNS resolve and check
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for info in addr_info:
            ip = info[4][0]
            if _is_private_ip(ip):
                return False
    except socket.gaierror:
        return False  # Invalid hostname

    return True


async def _check_reachable(url: str) -> bool:
    """Check if URL is reachable via HEAD request with timeout."""
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.head(url, allow_redirects=True) as resp:
                return resp.status < 500
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return False


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    endpoint: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v) < 1 or len(v) > 64:
            raise HTTPException(status_code=400, detail="Name must be 1-64 characters")
        # Sanitize: reject SQL injection and XSS attempts
        dangerous_patterns = [r"['\";]", r"<script", r"DROP\s+TABLE", r"UNION\s+SELECT"]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise HTTPException(status_code=400, detail=f"Invalid characters in name")
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _validate_url(v):
            raise HTTPException(status_code=400, detail="Invalid URL format or private IP detected (SSRF protection)")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) < 1 or len(v) > 64:
            raise HTTPException(status_code=400, detail="Name must be 1-64 characters")
        dangerous_patterns = [r"['\";]", r"<script", r"DROP\s+TABLE", r"UNION\s+SELECT"]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise HTTPException(status_code=400, detail=f"Invalid characters in name")
        return v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _validate_url(v):
            raise HTTPException(status_code=400, detail="Invalid URL format or private IP detected (SSRF protection)")
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Check endpoint reachability if provided
    if agent.endpoint:
        reachable = await _check_reachable(agent.endpoint)
        if not reachable:
            raise HTTPException(status_code=400, detail="Agent endpoint is not reachable")

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        endpoint=agent.endpoint,
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

    # Validate endpoint if provided
    if update.endpoint is not None:
        if not _validate_url(update.endpoint):
            raise HTTPException(status_code=400, detail="Invalid URL format or private IP detected (SSRF protection)")
        # Check reachability
        reachable = await _check_reachable(update.endpoint)
        if not reachable:
            raise HTTPException(status_code=400, detail="Agent endpoint is not reachable")

    for field, value in update.model_dump(exclude_unset=True).items():
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
