"""
Agent CRUD endpoints for the OpenAgents platform.

@contributor
  name: szamaniai-agent
  platform_instructions: >
    You are a general-purpose agent. Given the user's message, you should use the tools
    available to complete the task. Do what has been asked; nothing more, nothing less.
    When you complete the task, respond with a concise report covering what was done and
    any key findings.

    Guidelines:
    - For file searches: search broadly when you don't know where something lives.
      Use read_file when you know the specific file path.
    - For analysis: Start broad and narrow down. Use multiple search strategies
      if the first doesn't yield results.
    - Be thorough: Check multiple locations, consider different naming conventions,
      look for related files.
    - NEVER create files unless they're absolutely necessary.
    - ALWAYS prefer editing an existing file to creating a new one.
    - NEVER proactively create documentation files.
    - In your final response, share file paths (always absolute, never relative)
      that are relevant to the task.
    - For clear communication, avoid using emojis.
    - You operate in non-interactive mode: do not ask the user questions; proceed
      with available context.
    - Use tools only when necessary to obtain facts or make changes.
    - When the task is complete, return the final result as a normal model response
      (not a tool call) and stop.
    System prompt also includes full AIGON Enterprise Brain orchestration rules,
    WAR MODE directives, 20 Quality Gates, Parallel Execution Mandatory,
    and Law Omega enforcement. Full QWEN.md context loaded at session start.
  runtime:
    os: linux
    arch: x64
    home_dir: /root
    working_dir: /opt/projects/kraina
    shell: /bin/bash
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import httpx
from urllib.parse import urlparse
import ipaddress
import socket

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# RFC 1918 private ranges and special-purpose blocks to block for SSRF protection
PRIVATE_PREFIXES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(host: str) -> bool:
    """Check if a hostname resolves to a private/internal IP address."""
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in PRIVATE_PREFIXES)
    except ValueError:
        pass
    # Hostname is not a literal IP — resolve it
    try:
        addrs = socket.getaddrinfo(host, None)
        for family, _type, _proto, _cname, sockaddr in addrs:
            try:
                addr = ipaddress.ip_address(sockaddr[0])
                if any(addr in net for net in PRIVATE_PREFIXES):
                    return True
            except ValueError:
                continue
    except (socket.gaierror, OSError):
        pass  # Unresolvable — will be caught by reachability check
    return False


async def _validate_endpoint_url(endpoint: str) -> str:
    """
    Validate an agent endpoint URL:
    - Must be a valid http/https URL
    - Must not resolve to a private/internal IP (SSRF protection)
    - Must be reachable via HEAD request with 5s timeout
    Returns the validated endpoint string on success.
    """
    parsed = urlparse(endpoint)

    # Format validation: scheme must be http or https
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Invalid endpoint URL: must use http or https scheme",
        )

    # Must have a non-empty hostname
    host = parsed.hostname
    if not host:
        raise HTTPException(
            status_code=400,
            detail="Invalid endpoint URL: no hostname provided",
        )

    # SSRF protection: reject private/internal IPs
    if _is_private_ip(host):
        raise HTTPException(
            status_code=403,
            detail="Endpoint URL resolves to a private or internal IP address (SSRF protection)",
        )

    # Reachability check via HEAD request with 5s timeout
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(endpoint, follow_redirects=True)
            if response.status_code >= 500:
                raise HTTPException(
                    status_code=400,
                    detail=f"Endpoint unreachable: server returned {response.status_code}",
                )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=400,
            detail="Endpoint unreachable: HEAD request timed out after 5 seconds",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Endpoint unreachable: {str(e)}",
        )

    return endpoint


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    endpoint: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Agent name must not be empty")
        return v.strip()

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Endpoint must use http or https scheme")
        if not parsed.hostname:
            raise ValueError("Endpoint must include a hostname")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if v is not None and not v.strip():
            raise ValueError("Agent name must not be empty")
        return v.strip() if v else v

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        if v is not None:
            parsed = urlparse(v)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Endpoint must use http or https scheme")
            if not parsed.hostname:
                raise ValueError("Endpoint must include a hostname")
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    # Deep validation including SSRF and reachability
    validated_endpoint = await _validate_endpoint_url(agent.endpoint)

    new_agent = Agent(
        name=agent.name,
        endpoint=validated_endpoint,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return {"id": new_agent.id, "name": new_agent.name, "endpoint": new_agent.endpoint, "owner": user["address"]}


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

    update_data = update.model_dump(exclude_unset=True)
    # Deep-validate endpoint if being updated
    if "endpoint" in update_data:
        validated = await _validate_endpoint_url(update_data["endpoint"])
        update_data["endpoint"] = validated

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
