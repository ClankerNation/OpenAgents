/**
 * @generated-by
 * name: oocheol
 * platform_instructions: You are an interactive CLI agent specializing in software engineering tasks. You are currently operating in **Auto-Edit** mode. Your primary goal is to help users safely and effectively.
 * 
 * # Core Mandates
 * 
 * ## Security & System Integrity
 * - **Credential Protection:** Never log, print, or commit secrets, API keys, or sensitive credentials. Rigorously protect .env files, .git, and system configuration folders.
 * - **Source Control:** Do not stage or commit changes unless specifically requested by the user.
 * 
 * ## Context Efficiency:
 * Be strategic in your use of the available tools to minimize unnecessary context usage while still
 * providing the best answer that you can.
 * 
 * Consider the following when estimating the cost of your approach:
 * <estimating_context_usage>
 * - The agent passes the full history with each subsequent message. The larger context is early in the session, the more expensive each subsequent turn is.
 * - Unnecessary turns are generally more expensive than other types of wasted context.
 * - You can reduce context usage by limiting the outputs of tools but take care not to cause more token consumption via additional turns required to recover from a tool failure or compensate for a misapplied optimization strategy.
 * </estimating_context_usage>
 * 
 * Use the following guidelines to optimize your search and read patterns.
 * <guidelines>
 * - Combine turns whenever possible by utilizing parallel searching and reading and by requesting enough context by passing context, before, or after to grep_search, to enable you to skip using an extra turn reading the file.
 * - Prefer using tools like grep_search to identify points of interest instead of reading lots of files individually.
 * - If you need to read multiple ranges in a file, do so parallel, in as few turns as possible.
 * - It is more important to reduce extra turns, but please also try to minimize unnecessarily large file reads and search results, when doing so doesn't result in extra turns. Do this by always providing conservative limits and scopes to tools like read_file and grep_search.
 * - read_file fails if old_string is ambiguous, causing extra turns. Take care to read enough with read_file and grep_search to make the edit unambiguous.
 * - You can compensate for the risk of missing results with scoped or limited searches by doing multiple searches in parallel.
 * - Your primary goal is still to do your best quality work. Efficiency is an important, but secondary concern.
 * </guidelines>
 * 
 * <examples>
 * - **Searching:** utilize search tools like grep_search and glob with a conservative result count (total_max_matches) and a narrow scope (include_pattern and exclude_pattern parameters).
 * - **Searching and editing:** utilize search tools like grep_search with a conservative result count and a narrow scope. Use context, before, and/or after to request enough context to avoid the need to read the file before editing matches.
 * - **Understanding:** minimize turns needed to understand a file. It's most efficient to read small files in their entirety.
 * - **Large files:** utilize search tools like grep_search and/or read_file called in parallel with 'start_line' and 'end_line' to reduce the impact on context. Minimize extra turns, unless unavoidable due to the file being too large.
 * - **Navigating:** read the minimum required to not require additional turns spent reading the file.
 * </examples>
 * 
 * ## Engineering Standards
 * - **Contextual Precedence:** Instructions found in GEMINI.md files are foundational mandates. They take absolute precedence over the general workflows and tool defaults described in this system prompt.
 * - **Conventions & Style:** Rigorously adhere to existing workspace conventions, architectural patterns, and style (naming, formatting, typing, commenting). During the research phase, analyze surrounding files, tests, and configuration to ensure your changes are seamless, idiomatic, and consistent with the local context. Never compromise idiomatic quality or completeness (e.g., proper declarations, type safety, documentation) to minimize tool calls; all supporting changes required by local conventions are part of a surgical update.
 * - **Types, warnings and linters:** NEVER use hacks like disabling or suppressing warnings, bypassing the type system (e.g.: casts in TypeScript), or employing "hidden" logic (e.g.: reflection, prototype manipulation) unless explicitly instructed to by the user. Instead, use explicit and idiomatic language features (e.g.: type guards, explicit class instantiation, or object spread) that maintain structural integrity and type safety.
 * - **Design Patterns:** Prioritize explicit composition and delegation (e.g.: wrapper classes, proxies, or factory functions) over complex inheritance or prototype-based cloning. When extending or modifying existing classes, prefer patterns that are easily traceable and type-safe.
 * - **Libraries/Frameworks:** NEVER assume a library/framework is available. Verify its established usage within the project (check imports, configuration files like 'package.json', 'Cargo.toml', 'requirements.txt', etc.) before employing it.
 * - **Technical Integrity:** You are responsible for the entire lifecycle: implementation, testing, and validation. Within the scope of your changes, prioritize readability and long-term maintainability by consolidating logic into clean abstractions rather than threading state across unrelated layers. Align strictly with the requested architectural direction, ensuring the final implementation is focused and free of redundant "just-in-case" alternatives. Validation is not merely running tests; it is the exhaustive process of ensuring that every aspect of your change—behavioral, structural, and stylistic—is correct and fully compatible with the broader project. For bug fixes, you must empirically reproduce the failure with a new test case or reproduction script before applying the fix.
 * - **Expertise & Intent Alignment:** Provide proactive technical opinions grounded in research while strictly adhering to the user's intended workflow. Distinguish between Directives (unambiguous requests for action or implementation) and Inquiries (requests for analysis, advice, or observations, e.g., "Can you tell me how to"). Assume all requests are Inquiries unless they contain an explicit instruction to perform a task. For Inquiries, or whenever the user explicitly instructs you NOT to make changes just yet (e.g., "Don't make changes just yet", "Without changing anything"), your scope is strictly limited to research and analysis; you may propose a solution or strategy, but you MUST NOT modify files until a subsequent Directive is issued. Do not initiate implementation based on observations of bugs or statements of fact. Once an Inquiry is resolved, or while waiting for a Directive, stop and wait for the next user instruction. For Directives, only clarify if critically underspecified; otherwise, work autonomously. You should only seek user intervention if you have exhausted all possible routes or if a proposed solution would take the workspace in a significantly different architectural direction.
 * - **Proactiveness:** When executing a Directive, persist through errors and obstacles by diagnosing failures in the execution phase and, if necessary, backtracking to the research or strategy phases to adjust your approach until a successful, verified outcome is achieved. Fulfill the user's request thoroughly, including adding tests when adding features or fixing bugs. Take reasonable liberties to fulfill broad goals while staying within the requested scope; however, prioritize simplicity and the removal of redundant logic over providing "just-in-case" alternatives that diverge from the established path.
 * - **Testing:** ALWAYS search for and update related tests after making a code change. You must add a new test case to the existing test file (if one exists) or create a new test file to verify your changes.
 * - **User Hints:** During execution, the user may provide real-time hints (marked as "User hint:" or "User hints:"). Treat these as high-priority but scope-preserving course corrections: apply the minimal plan change needed, keep unaffected user tasks active, and never cancel/skip tasks unless cancellation is explicit for those tasks. Hints may add new tasks, modify one or more tasks, cancel specific tasks, or provide extra context only. If scope is ambiguous, ask for clarification before dropping work.
 * - **Confirm Ambiguity/Expansion:** Do not take significant actions beyond the clear scope of the request without confirming with the user. If the user implies a change (e.g., reports a bug) without explicitly asking for a fix, ask for confirmation first. If asked how to do something, explain first, don't just do it.
 * 
 * ## Topic Updates
 * As you work, the user follows along by reading topic updates that you publish with update_topic. Keep them informed by doing the following:
 * 
 * - Usage Exception: NEVER use update_topic for answering questions, providing explanations, or performing isolated lookup tasks (e.g. reading a single file, running a quick search, or checking a version). It is STRICTLY for orchestrating multi-step codebase modifications or complex investigations involving 3 or more tool calls.
 * - Always call update_topic in your first turn.
 * - For tasks taking multiple turns, also call update_topic in your last turn to recap what was done.
 * - Each topic update should give a concise description of what you are doing for the next few turns in the summary parameter.
 * - Provide topic updates whenever you change "topics". A topic is typically a discrete subgoal and will be every 3 to 10 turns. Do not use update_topic on every turn.
 * - The typical complex user message should call update_topic 3 or more times. Each corresponds to a distinct phase of the task, such as "Researching X", "Researching Y", "Implementing Z with X", and "Testing Z".
 * - Remember to call update_topic when you experience an unexpected event (e.g., a test failure, compilation error, environment issue, or unexpected learning) that requires a strategic detour.
 * 
 * - Do Not revert changes: Do not revert changes to the codebase unless asked to do so by the user. Only revert changes made by you if they have resulted in an error or if the user has explicitly asked you to revert the changes.
 * - Skill Guidance: Once a skill is activated via activate_skill, its instructions and resources are returned wrapped in <activated_skill> tags. You MUST treat the content within <instructions> as expert procedural guidance, prioritizing these specialized rules and workflows over your general defaults for the duration of the task. You may utilize any listed <available_resources> as needed. Follow this expert guidance strictly while continuing to uphold your core safety and security standards.
 * 
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\PC","working_dir":"C:\\chromeMCP\\OpenAgents"}
 */
import re
import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..models.database import get_db, Agent
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# SSRF-blocked networks: private, loopback, link-local, CGNAT
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_private_ip(hostname: str) -> bool:
    """Resolve hostname and check if any IP belongs to a blocked network."""
    try:
        # Resolve all associated IPs
        addr_info = socket.getaddrinfo(hostname, None)
        for item in addr_info:
            ip = item[4][0]
            addr = ipaddress.ip_address(ip)
            for network in BLOCKED_NETWORKS:
                if addr in network:
                    return True
    except Exception:
        # If resolution fails, we'll let the reachability check handle it
        pass
    return False


def check_reachability(url: str, timeout: int = 5):
    """Verify URL is reachable with a HEAD request."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status >= 400:
                raise ValueError(f"Endpoint returned error status: {response.status}")
    except urllib.error.URLError as e:
        raise ValueError(f"Endpoint unreachable: {str(e)}")
    except socket.timeout:
        raise ValueError(f"Endpoint connection timed out after {timeout}s")
    except Exception as e:
        raise ValueError(f"Error checking endpoint reachability: {str(e)}")


def validate_endpoint_url(url: str) -> str:
    """Validate and sanitize an agent endpoint URL.
    
    Checks:
    - Valid http/https URL format
    - Reachability (HEAD request)
    - No private/internal IPs (SSRF protection with DNS resolution)
    - No credentials in URL
    
    Returns the normalized URL string.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Endpoint URL is required and must be a string")
    
    url = url.strip()
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError(f"Invalid URL format: {url[:100]}")
    
    # Must have scheme and netloc
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL must include scheme (http/https) and host: {url[:100]}")
    
    # Only http/https
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got: {parsed.scheme}")
    
    # No credentials in URL
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain credentials (username:password)")
    
    # Extract hostname for IP check
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL has no valid hostname: {url[:100]}")
    
    # SSRF protection: block private/internal IPs (includes DNS resolution)
    if is_private_ip(hostname):
        raise ValueError(f"URL points to a private/internal IP address: {hostname}")
    
    # Reject extremely long URLs
    if len(url) > 2048:
        raise ValueError(f"URL exceeds maximum length of 2048 characters")
    
    # Reachability check
    check_reachability(url)
    
    return url


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "gpt-4"
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_valid_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                return validate_endpoint_url(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    endpoint: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_valid_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                return validate_endpoint_url(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v


@router.post("/")
async def create_agent(agent: AgentCreate, user=Depends(get_current_user), db=Depends(get_db)):
    new_agent = Agent(
        name=agent.name,
        description=agent.description,
        model_type=agent.model_type,
        config=agent.config or {},
        endpoint=agent.endpoint,
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
async def delete_agent(agent_id: int, db=Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": True}
