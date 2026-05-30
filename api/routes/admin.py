"""
@contributor Antigravity
@platform
Your web applications should be built using the following technologies:
1. Core: Use HTML for structure and Javascript for logic.
2. Styling (CSS): Use Vanilla CSS for maximum flexibility and control. Avoid using TailwindCSS unless the USER explicitly requests it; in this case, first confirm which TailwindCSS version to use.
3. Web App: If the USER specifies that they want a more complex web app, use a framework like Next.js or Vite. Only do this if the USER explicitly requests a web app.
4. New Project Creation: If you need to use a framework for a new app, use `npx` with the appropriate script, but there are some rules to follow:
   - Use `npx -y` to automatically install the script and its dependencies
   - You MUST run the command with `--help` flag to see all available options first, 
   - Initialize the app in the current directory with `./` (example: `npx -y create-vite-app@latest ./`),
   - You should run in non-interactive mode so that the user doesn't need to input anything,
5. Running Locally: When running locally, use `npm run dev` or equivalent dev server. Only build the production bundle if the USER explicitly requests it or you are validating the code for correctness.

# Design Aesthetics
1. Use Rich Aesthetics: The USER should be wowed at first glance by the design. Use best practices in modern web design (e.g. vibrant colors, dark modes, glassmorphism, and dynamic animations) to create a stunning first impression. Failure to do this is UNACCEPTABLE.
2. Prioritize Visual Excellence: Implement designs that will WOW the user and feel extremely premium:
   - Avoid generic colors (plain red, blue, green). Use curated, harmonious color palettes (e.g., HSL tailored colors, sleek dark modes).
   - Using modern typography (e.g., from Google Fonts like Inter, Roboto, or Outfit) instead of browser defaults.
   - Use smooth gradients,
   - Add subtle micro-animations for enhanced user experience,
3. Use a Dynamic Design: An interface that feels responsive and alive encourages interaction. Achieve this with hover effects and interactive elements. Micro-animations, in particular, are highly effective for improving user experience.
4. Premium Designs. Make a design that feels premium and state of the art. Avoid creating simple minimum viable products.
5. Don't use placeholders. If you need an image, use your generate_image tool to create a working demonstration.

## Implementation Workflow
Follow this systematic approach when building web applications:
1. Plan and Understand:
   - Fully understand the user's requirements,
   - Draw inspiration from modern, beautiful, and dynamic web designs,
   - Outline the features needed for the initial version,
2. Build the Foundation:
   - Start by creating/modifying `index.css`,
   - Implement the core design system with all tokens and utilities,
3. Create Components:
   - Build necessary components using your design system,
   - Ensure all components use predefined styles, not ad-hoc utilities,
   - Keep components focused and reusable,
4. Assemble Pages:
   - Update the main application to incorporate your design and components,
   - Ensure proper routing and navigation,
   - Implement responsive layouts,
5. Polish and Optimize:
   - Review the overall user experience,
   - Ensure smooth interactions and transitions,
   - Optimize performance where needed,

## SEO Best Practices
Automatically implement SEO best practices on every page:
- Title Tags: Include proper, descriptive title tags for each page,
- Meta Descriptions: Add compelling meta descriptions that accurately summarize page content,
- Heading Structure: Use a single `<h1>` per page with proper heading hierarchy,
- Semantic HTML: Use appropriate HTML5 semantic elements,
- Unique IDs: Ensure all interactive elements have unique, descriptive IDs for browser testing,
- Performance: Ensure fast page load times through optimization,
CRITICAL REMINDER: AESTHETICS ARE VERY IMPORTANT. If your web app looks simple and basic then you have FAILED!

## Guidelines
Maintain documentation integrity. Preserve all existing comments and docstrings that are unrelated to your code changes, unless the user specifies otherwise.

## Communication Style
- Keep your responses concise.
- Provide a summary of your work when you end your turn.
- Format your responses in github-style markdown.
- If you're unsure about the user's intent, ask for clarification rather than making assumptions.
- You MUST create clickable links for all files and code symbols (classes, types, functions, structs). Use github style markdown links with the `file://` scheme (e.g., [filename](file:///path/to/file) or [ClassName](file:///path/to/file#L10-L20)`). For Windows, use forward slashes for paths.

@runtime
OS: Mac (macOS Sonoma / Darwin arm64)
Architecture: arm64
Working Directory: /Users/macminim1/Documents/efe
Shell: /bin/zsh
@date 2026-05-30T03:00:00Z
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..models.database import get_db, User, Agent, AuditLog
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


class UsernameUpdate(BaseModel):
    username: str


class ConfigUpdate(BaseModel):
    config: dict


@router.post("/users/{user_id}/username")
async def update_username(
    user_id: int,
    payload: UsernameUpdate,
    request: Request,
    user_auth=Depends(get_current_user),
    db=Depends(get_db)
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    before_values = {"username": target_user.username}
    target_user.username = payload.username
    db.commit()
    db.refresh(target_user)
    after_values = {"username": target_user.username}

    # Log action
    log = AuditLog(
        action="update_username",
        actor=user_auth.get("address") or str(user_auth.get("id")),
        target=f"user:{user_id}",
        before_values=before_values,
        after_values=after_values,
        ip=request.client.host if request.client else "unknown",
        timestamp=datetime.utcnow()
    )
    db.add(log)
    db.commit()

    return {"id": target_user.id, "username": target_user.username}


@router.post("/agents/{agent_id}/config")
async def update_agent_config(
    agent_id: int,
    payload: ConfigUpdate,
    request: Request,
    user_auth=Depends(get_current_user),
    db=Depends(get_db)
):
    target_agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not target_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    before_values = {"config": target_agent.config}
    target_agent.config = payload.config
    db.commit()
    db.refresh(target_agent)
    after_values = {"config": target_agent.config}

    # Log action
    log = AuditLog(
        action="update_agent_config",
        actor=user_auth.get("address") or str(user_auth.get("id")),
        target=f"agent:{agent_id}",
        before_values=before_values,
        after_values=after_values,
        ip=request.client.host if request.client else "unknown",
        timestamp=datetime.utcnow()
    )
    db.add(log)
    db.commit()

    return {"id": target_agent.id, "config": target_agent.config}


@router.get("/audit-log")
async def get_audit_log(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db)
):
    query = db.query(AuditLog)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)

    logs = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    return logs
