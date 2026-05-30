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

import os
os.environ["JWT_SECRET"] = "test_secret"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.main import app
from api.models.database import Base, get_db, User, Agent, AuditLog
from api.middleware.auth import get_current_user

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_audit.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Mock current user dependency
mock_user = {"id": 1, "address": "0x1234567890123456789012345678901234567890", "roles": ["admin"]}
def override_get_current_user():
    return mock_user

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    # Seed a user and an agent for testing updates
    u = User(id=1, address="0x1234567890123456789012345678901234567890", username="test_user")
    a = Agent(id=1, name="test_agent", config={}, owner_id=1)
    db.add(u)
    db.add(a)
    db.commit()
    yield
    db.close()
    Base.metadata.drop_all(bind=engine)

def test_admin_action_creates_audit_record():
    # Update username
    response = client.post("/admin/users/1/username", json={"username": "new_username"})
    assert response.status_code == 200
    assert response.json()["username"] == "new_username"

    # Query audit logs
    logs_res = client.get("/admin/audit-log")
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert len(logs) == 1
    assert logs[0]["action"] == "update_username"
    assert logs[0]["actor"] == mock_user["address"]
    assert logs[0]["target"] == "user:1"
    assert logs[0]["before_values"] == {"username": "test_user"}
    assert logs[0]["after_values"] == {"username": "new_username"}

def test_audit_logs_query_filters():
    # Trigger log 1
    client.post("/admin/users/1/username", json={"username": "user_a"})
    # Trigger log 2
    client.post("/admin/agents/1/config", json={"config": {"key": "val"}})

    # Query filter by action
    res = client.get("/admin/audit-log?action=update_agent_config")
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) == 1
    assert logs[0]["action"] == "update_agent_config"

    # Query filter by actor
    res2 = client.get(f"/admin/audit-log?actor={mock_user['address']}")
    assert res2.status_code == 200
    assert len(res2.json()) == 2

def test_audit_log_immutability():
    client.post("/admin/users/1/username", json={"username": "user_b"})

    db = TestingSessionLocal()
    log = db.query(AuditLog).first()
    assert log is not None

    # Try updating
    with pytest.raises(ValueError, match="immutable"):
        log.action = "malicious_change"
        db.commit()

    db.rollback()

    # Try deleting
    with pytest.raises(ValueError, match="immutable"):
        db.delete(log)
        db.commit()
    db.close()
