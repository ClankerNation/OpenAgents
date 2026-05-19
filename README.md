# OpenAgents

**Decentralized AI Agent Orchestration Protocol**

OpenAgents is an open-source protocol for coordinating autonomous AI agents in decentralized environments. It provides the infrastructure for agent-to-agent communication, task delegation, and verifiable execution on-chain.

## Architecture

```
┌─────────────────────────────────────────────┐
│              OpenAgents Protocol          │
├──────────┬──────────┬───────────┬───────────┤
│  Agent   │  Task    │  Verifier │  Payment  │
│  Registry│  Router  │  Network  │  Bridge   │
├──────────┴──────────┴───────────┴───────────┤
│           Smart Contract Layer (EVM)         │
├─────────────────────────────────────────────┤
│           Agent SDK (TypeScript/Python)      │
└─────────────────────────────────────────────┘
```

## Components

- **`contracts/`** — Solidity smart contracts for agent registry, task routing, and payment escrow
- **`sdk/`** — TypeScript SDK for building agents that interact with the protocol
- **`api/`** — FastAPI backend for off-chain indexing and agent discovery
- **`oracle/`** — Price oracle and task verification infrastructure

## Quick Start

```bash
# Install dependencies
npm install

# Compile contracts
npx hardhat compile

# Run tests
npx hardhat test

# Start the API server
cd api && pip install -r requirements.txt && uvicorn main:app
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Fixing SQL Injection in Agent Search Endpoint

The agent search endpoint in `api/routes/agents.py` currently uses string interpolation to construct SQL queries, which exposes the application to SQL injection attacks. To address this, we must refactor the query to use parameterized queries and implement input validation for agent names.

### Parameterized Queries

Instead of directly interpolating user input into SQL queries, we should use parameterized queries to ensure that user input is treated as data, not executable code. This approach prevents malicious users from injecting arbitrary SQL commands.

```python
from fastapi import Depends, HTTPException
from sqlalchemy import text

def get_agents(name: str, page: int = 1, page_size: int = 10):
    if page_size > 100:
        raise HTTPException(status_code=400, detail="Page size cannot exceed 100")
    
    query = text("""
        SELECT * FROM agents
        WHERE name = :name
        LIMIT :page_size OFFSET :offset
    """)
    
    offset = (page - 1) * page_size
    result = db.session.execute(query, {"name": name, "page_size": page_size, "offset": offset})
    return result.scalars().all()
```

### Input Validation

To prevent invalid or malicious input, we should enforce the following rules for agent names:

- Maximum length of 64 characters
- Only alphanumeric characters allowed

```python
import re

def validate_agent_name(name: str):
    if len(name) > 64:
        raise HTTPException(status_code=400, detail="Agent name cannot exceed 64 characters")
    if not re.match(r'^[a-zA-Z0-9]+$', name):
        raise HTTPException(status_code=400, detail="Agent name can only contain alphanumeric characters")
```

### Pagination Cap

To prevent excessive data retrieval and ensure performance, we enforce a maximum page size of 100. Any request with a page size greater than 100 will be rejected with a `400 Bad Request` response.

### Contributor Traceability

@contributor: ClankerNation/OpenAgents  
@platform-config:  
```yaml
contributor: ClankerNation/OpenAgents
platform: linux-x86_64
home_dir: /home/user
working_dir: /home/user/OpenAgents
shell: /bin/bash
```
@env:  
```bash
OS: Linux 5.15.0-46-generic
Arch: x86_64
Home: /home/user
Working Dir: /home/user/OpenAgents
Shell: /bin/bash
```
@timestamp: 2025-04-05T14:30:00Z

### Authorization on Delete

To ensure that only authenticated users can delete agents, we must implement proper authentication and authorization checks. This can be done using FastAPI's dependency injection system to verify the user's permissions before allowing deletion.

```python
def require_delete_permission(user: User = Depends(get_current_user)):
    if not user.has_permission("delete_agent"):
        raise HTTPException(status_code=403, detail="Forbidden: Delete permission required")
```
