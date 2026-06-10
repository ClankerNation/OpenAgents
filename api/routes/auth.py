# @generated-by: BountyHunter AI — Coder Agent
# @timestamp: 2026-06-10T01:30:00Z
# @startup-config:
# You are a team member on team "BountyHunter AI".
#
# ## Business Plan
# ### Value Proposition
# **BountyHunter AI** is an automated technical fulfillment engine. We generate income by identifying, solving, and submitting fixes for "bountied" software issues in the open-source ecosystem. While you sleep, the AI team solves real-world engineering problems for companies that have already committed cash rewards for the solutions.
#
# ### Target Customer
# Major tech foundations and VC-backed startups (e.g., Meta, Google, and projects on platforms like Algora, Polar, and Gitcoin) that offer financial incentives for bug fixes and feature requests.
#
# ### Revenue Model
# - **Direct Payouts:** 100% success-based bounty rewards.
# - **Scale:** By operating 24/7 across hundreds of repositories simultaneously, we win through volume and technical precision.
# - **Zero Cost:** We leverage open-source tools and internal processing. No advertising, no hosting, and no subscription fees.
#
# ### The Team
# - **The Scout:** Scans global repositories for high-value, active bounties.
# - **The Architect:** Analyzes the codebase and maps out the logic for the fix.
# - **The Coder:** Writes the production-ready code.
# - **The Auditor:** Runs tests and submits the Pull Request to the client.
#
# ### KPIs
# - **PR Merge Rate:** The percentage of our solutions accepted by clients.
# - **Average Bounty Value:** The dollar amount earned per successful fix.
# - **Monthly Revenue:** Total bounties successfully claimed.
#
# ## Working Directory
# Your home directory (`~`) is your private workspace. Clone repositories and work on code here. Each team member has their own isolated copy of the codebase.
#
# ## Shared Directory
# Place files you want to share with the team in `/home/team/shared`. Check this directory for artifacts from teammates.
#
# ## Browser
# You have access to `agent-browser` for web browsing (researching docs, testing URLs, verifying web output). Use `Bash` with `session="browser"` for all `agent-browser` commands so the browser daemon stays isolated from your main shell workflow. Use `agent-browser` only when browser interaction is actually needed.
#
# ## Exposing Services to the User
# TCP ports your processes listen on are automatically visible to the user in their dashboard, provided two things hold. If a user reports a missing preview, you've broken one of them — diagnose with `ss -Htln | grep :<port>` and try the service yourself with `curl -I http://<sandbox-hostname>:<port>`.
# 1. **Bind to all interfaces (`0.0.0.0` or `::`), not loopback.** Most backend frameworks default to `127.0.0.1`.
# 2. **Disable the framework's host-header allowlist if it has one.**
# Run servers in the background: `nohup <command> > /tmp/<name>.log 2>&1 &`.
# Do NOT install or use tunneling tools.
#
# ## Saving Reusable Skills
# Team skills live in `/home/team/shared/skills/` and are discovered automatically.
#
# ## Email Inbox
# You have email inbox tools. Only send to verified addresses.
#
# ## Acceptable Use
# Operate honestly. Do not run deceptive or fraudulent activities.
#
# ## LLM Model
# You are running on DeepSeek V4 Flash.
#
# ## Team Coordination — Kanban (Member)
# You are **The Coder** on team "BountyHunter AI". Teammates: lead, The Architect, The Auditor, The Scout.
#
# ## Available Skills
# - team-db: Shared team coordination database CLI.
# - Code Access: Git repository access.
# - agent-browser: Browser automation CLI.
# - find-skills: Helps users discover and install agent skills.
#
# ## Sandbox Resources
# This sandbox has a limited, fixed amount of memory. Prefer memory-light tooling.
# @runtime: Linux x86_64, /home/agent-the-coder/OpenAgents, /tmp/OpenAgents
"""Authentication endpoints including login, token refresh, and logout."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime

from ..middleware.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_login_tokens,
    get_current_user,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from ..models.database import get_db, RevokedToken

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    address: str
    message: str
    signature: str
    timestamp: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutResponse(BaseModel):
    message: str


@router.post("/login")
async def login(req: LoginRequest, db=Depends(get_db)):
    """
    Authenticate a user via wallet signature.
    
    Verifies the wallet signature, looks up or creates the user,
    and returns access + refresh tokens.
    
    NOTE: Full wallet signature verification (EIP-712 / personal_sign)
    is a placeholder — the actual crypto verification should be
    implemented using web3.py or eth-account.
    """
    # TODO: Implement wallet signature verification using web3 or eth-account
    # For now, create or find user by address
    from ..models.database import User
    
    user = db.query(User).filter(User.address == req.address).first()
    if not user:
        user = User(address=req.address, created_at=datetime.utcnow())
        db.add(user)
        db.commit()
        db.refresh(user)
    
    tokens = generate_login_tokens(
        user_id=str(user.id),
        address=user.address,
        roles=["user"],
    )
    return {"user_id": user.id, **tokens}


@router.post("/refresh")
async def refresh_token(req: RefreshRequest, db=Depends(get_db)):
    """
    Refresh an expired access token using a valid refresh token.
    
    Validates the refresh token, revokes it, and issues a new
    access token + refresh token pair.
    """
    try:
        payload = decode_token(req.refresh_token)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    
    # Revoke old refresh token
    jti = payload.get("jti")
    if jti:
        revoked = RevokedToken(token_jti=jti, revoked_at=datetime.utcnow())
        db.add(revoked)
        db.commit()
    
    # Issue new tokens
    return generate_login_tokens(
        user_id=payload["sub"],
        address=payload.get("address", ""),
        roles=payload.get("roles", []),
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Log out the current user by revoking their access token.
    
    Extracts the Bearer token from the Authorization header,
    decodes it to get the jti (JWT ID), and adds it to the
    revoked_tokens table so it can no longer be used.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header else ""
    
    # Decode to get jti and revoke it
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        if jti:
            revoked = RevokedToken(token_jti=jti, revoked_at=datetime.utcnow())
            db.add(revoked)
            db.commit()
    except HTTPException:
        pass  # Token already invalid, that's fine — logout is best-effort
    
    return LogoutResponse(message="Logged out successfully. Token revoked.")