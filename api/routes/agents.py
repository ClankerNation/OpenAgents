"""Agent CRUD endpoints for the OpenAgents platform."""

import asyncio
from datetime import datetime
import ipaddress
import socket
import ssl
from typing import Any, Dict, List, NamedTuple, Optional, Union
from urllib.parse import SplitResult, urljoin, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

ENDPOINT_REACHABILITY_TIMEOUT_SECONDS = 5.0
MAX_ENDPOINT_REDIRECTS = 3
_ALLOWED_ENDPOINT_SCHEMES = {"http", "https"}
IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


class EndpointTarget(NamedTuple):
    url: str
    parsed: SplitResult
    port: int
    addresses: List[IPAddress]


class EndpointProbeResponse(NamedTuple):
    status_code: int
    headers: Dict[str, str]


def _validation_error(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _parse_endpoint(endpoint: str):
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise _validation_error("Agent endpoint is required")
    if any(ord(char) < 32 or ord(char) == 127 for char in endpoint):
        raise _validation_error("Agent endpoint contains invalid control characters")

    normalized = endpoint.strip()
    try:
        parsed = urlsplit(normalized)
        port = parsed.port or (80 if parsed.scheme.lower() == "http" else 443)
    except ValueError as exc:
        raise _validation_error("Agent endpoint must be a valid http/https URL") from exc

    if parsed.scheme.lower() not in _ALLOWED_ENDPOINT_SCHEMES or not parsed.hostname:
        raise _validation_error("Agent endpoint must be a valid http/https URL")
    if parsed.username or parsed.password:
        raise _validation_error("Agent endpoint must not include URL credentials")

    return normalized, parsed, port


def _is_internal_address(address: IPAddress) -> bool:
    return not address.is_global


def _resolve_hostname_addresses(hostname: str, port: int) -> List[IPAddress]:
    try:
        return [ipaddress.ip_address(hostname)]
    except ValueError:
        pass

    try:
        addrinfo = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise _validation_error("Agent endpoint hostname could not be resolved") from exc

    addresses: List[IPAddress] = []
    for family, _, _, _, sockaddr in addrinfo:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            continue
        addresses.append(ipaddress.ip_address(sockaddr[0]))

    if not addresses:
        raise _validation_error("Agent endpoint hostname could not be resolved")

    return addresses


def _validate_endpoint_target(endpoint: str) -> EndpointTarget:
    normalized, parsed, port = _parse_endpoint(endpoint)
    addresses = _resolve_hostname_addresses(parsed.hostname, port)

    if any(_is_internal_address(address) for address in addresses):
        raise _validation_error("Agent endpoint must not resolve to a private/internal IP")

    return EndpointTarget(
        url=normalized,
        parsed=parsed,
        port=port,
        addresses=addresses,
    )


def _endpoint_host_header(target: EndpointTarget) -> str:
    hostname = target.parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if target.parsed.port is not None:
        return f"{hostname}:{target.parsed.port}"
    return hostname


def _endpoint_request_target(target: EndpointTarget) -> str:
    path = target.parsed.path or "/"
    if target.parsed.query:
        return f"{path}?{target.parsed.query}"
    return path


def _parse_head_response(raw_headers: bytes) -> EndpointProbeResponse:
    if not raw_headers:
        raise _validation_error("Agent endpoint is unreachable")

    header_text = raw_headers.decode("iso-8859-1", errors="replace")
    lines = header_text.split("\r\n")
    status_parts = lines[0].split(" ", 2)
    if len(status_parts) < 2 or not status_parts[1].isdigit():
        raise _validation_error("Agent endpoint returned an invalid HTTP response")

    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.lower()] = value.strip()

    return EndpointProbeResponse(status_code=int(status_parts[1]), headers=headers)


async def _read_head_response(reader: asyncio.StreamReader) -> EndpointProbeResponse:
    try:
        raw_headers = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"),
            timeout=ENDPOINT_REACHABILITY_TIMEOUT_SECONDS,
        )
    except asyncio.IncompleteReadError as exc:
        raw_headers = exc.partial
    except asyncio.LimitOverrunError as exc:
        raise _validation_error("Agent endpoint response headers are too large") from exc
    except asyncio.TimeoutError as exc:
        raise _validation_error("Agent endpoint reachability check timed out") from exc

    return _parse_head_response(raw_headers)


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    try:
        await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
    except (asyncio.TimeoutError, OSError, ssl.SSLError):
        pass


async def _request_endpoint_head(target: EndpointTarget) -> EndpointProbeResponse:
    last_timeout = False
    use_tls = target.parsed.scheme.lower() == "https"
    tls_context = ssl.create_default_context() if use_tls else None

    for address in target.addresses:
        writer: Optional[asyncio.StreamWriter] = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host=address.compressed,
                    port=target.port,
                    ssl=tls_context,
                    server_hostname=target.parsed.hostname if use_tls else None,
                ),
                timeout=ENDPOINT_REACHABILITY_TIMEOUT_SECONDS,
            )
            request = (
                f"HEAD {_endpoint_request_target(target)} HTTP/1.1\r\n"
                f"Host: {_endpoint_host_header(target)}\r\n"
                "User-Agent: OpenAgents endpoint validator\r\n"
                "Accept: */*\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii")
            writer.write(request)
            await asyncio.wait_for(
                writer.drain(),
                timeout=ENDPOINT_REACHABILITY_TIMEOUT_SECONDS,
            )
            return await _read_head_response(reader)
        except asyncio.TimeoutError:
            last_timeout = True
        except (OSError, ssl.SSLError, ValueError):
            last_timeout = False
        finally:
            if writer is not None:
                await _close_writer(writer)

    if last_timeout:
        raise _validation_error("Agent endpoint reachability check timed out")
    raise _validation_error("Agent endpoint is unreachable")


async def validate_agent_endpoint(endpoint: str) -> str:
    """Validate endpoint format, SSRF safety, and reachability."""

    original_target = _validate_endpoint_target(endpoint)
    current_target = original_target

    for _ in range(MAX_ENDPOINT_REDIRECTS + 1):
        response = await _request_endpoint_head(current_target)

        if 300 <= response.status_code < 400:
            redirect_location = response.headers.get("location")
            if not redirect_location:
                raise _validation_error("Agent endpoint redirect is missing a Location header")
            current_target = _validate_endpoint_target(
                urljoin(current_target.url, redirect_location)
            )
            continue

        if response.status_code == 405:
            return original_target.url

        if response.status_code >= 400:
            raise _validation_error("Agent endpoint is unreachable")

        return original_target.url

    raise _validation_error("Agent endpoint has too many redirects")


def _endpoint_from_config(config: Optional[Dict[str, Any]]) -> Optional[str]:
    if not config or "endpoint" not in config:
        return None

    endpoint = config["endpoint"]
    if not isinstance(endpoint, str):
        raise _validation_error("Agent endpoint must be a string")
    return endpoint


def _extract_agent_endpoint(
    endpoint: Optional[str],
    config: Optional[Dict[str, Any]],
    *,
    required: bool,
) -> Optional[str]:
    config_endpoint = _endpoint_from_config(config)
    if endpoint is not None and config_endpoint is not None and endpoint != config_endpoint:
        raise _validation_error("Agent endpoint field must match config.endpoint")

    selected_endpoint = endpoint if endpoint is not None else config_endpoint
    if required and selected_endpoint is None:
        raise _validation_error("Agent endpoint is required")

    return selected_endpoint


def _merge_agent_config(
    existing_config: Optional[Dict[str, Any]],
    provided_config: Optional[Dict[str, Any]],
    validated_endpoint: Optional[str],
) -> Dict[str, Any]:
    merged_config = dict(existing_config or {})
    if provided_config is not None:
        merged_config.update(provided_config)
    if validated_endpoint is not None:
        merged_config["endpoint"] = validated_endpoint
    return merged_config


class AgentCreate(BaseModel):
    name: str  # BUG: No validation — name can contain SQL injection, XSS, or be empty
    endpoint: Optional[str] = None
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[Dict[str, Any]] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    endpoint = _extract_agent_endpoint(agent.endpoint, agent.config, required=True)
    if endpoint is None:
        raise _validation_error("Agent endpoint is required")
    validated_endpoint = await validate_agent_endpoint(endpoint)
    config = _merge_agent_config(None, agent.config, validated_endpoint)

    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=config,
        owner_id=user["id"],
        created_at=datetime.utcnow(),
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return {
        "id": new_agent.id,
        "name": new_agent.name,
        "owner": user["address"],
        "endpoint": validated_endpoint,
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

    updates = update.model_dump(exclude_unset=True)
    config = updates.pop("config", None)
    endpoint = _extract_agent_endpoint(updates.pop("endpoint", None), config, required=False)

    validated_endpoint = None

    if endpoint is not None:
        validated_endpoint = await validate_agent_endpoint(endpoint)

    if endpoint is not None or config is not None:
        updates["config"] = _merge_agent_config(agent.config, config, validated_endpoint)

    for field, value in updates.items():
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
