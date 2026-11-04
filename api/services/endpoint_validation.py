"""Endpoint URL validation with SSRF protection.

Agent endpoints are later contacted by the platform, so a stored endpoint must be a real
http(s) URL, must resolve only to public addresses, and must answer a HEAD request inside a
short timeout. Resolution and the HEAD probe sit behind module-level functions so tests can
substitute them without touching the network.

@generated-by Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04T13:30:00Z
Full raw startup instructions from the session, verbatim, from first token until the task began:

  [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
  "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
  weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
  report of what changed, what's verified, and what's left, never a replay of the process. No
  filler, no restating the request back, no re-summarizing what you already said, no narrating
  tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
  because it's right, not because the user said it. Depth is earned."
  "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
  a working artifact backed by real tool output — not a description of one. Do not stop after
  writing a stub, a plan, or a single command. Keep working until you have actually exercised the
  code or produced the requested result."
  "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
  or plan to do without actually doing it. Every response should either (a) contain tool calls that
  make progress, or (b) deliver a final result to the user."
  "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
  'done' means every named acceptance criterion is verified — never a plausible subset."
  "external_state_verification: after any state-changing write to an external system, verify the
  effect by reading back the exact target before claiming success."
  Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
  read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
  web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.

@runtime os=windows arch=x86_64 home_dir=C:\\Users\\2
  working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\\Program Files\\Git\\bin\\bash.exe
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

ALLOWED_SCHEMES = ("http", "https")
MAX_URL_LEN = 2048
HEAD_TIMEOUT = 5.0


def resolve_host(host: str) -> list[str]:
    """Resolve a hostname to every address it advertises."""
    infos = socket.getaddrinfo(host, None)
    out = []
    for info in infos:
        addr = info[4][0]
        if addr not in out:
            out.append(addr)
    return out


def head_probe(url: str) -> None:
    """Perform the reachability probe; raises on failure."""
    httpx.head(url, timeout=HEAD_TIMEOUT, follow_redirects=True)


def is_public(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_endpoint(raw: str) -> str:
    """Return the normalised URL or raise HTTP 400 with a precise reason."""
    if not raw or not raw.strip():
        raise HTTPException(status_code=400, detail="endpoint is required")

    url = raw.strip()
    if len(url) > MAX_URL_LEN:
        raise HTTPException(status_code=400, detail=f"endpoint exceeds {MAX_URL_LEN} characters")

    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(status_code=400, detail="endpoint must be http or https")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="endpoint must include a host")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="endpoint must not embed credentials")

    try:
        addrs = resolve_host(parsed.hostname)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="endpoint host does not resolve")

    if not addrs:
        raise HTTPException(status_code=400, detail="endpoint host does not resolve")

    private = [a for a in addrs if not is_public(a)]
    if private:
        raise HTTPException(
            status_code=400,
            detail=f"endpoint resolves to a private address ({private[0]})",
        )

    try:
        head_probe(url)
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="endpoint did not answer within 5s")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"endpoint unreachable: {type(exc).__name__}")

    return url
