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

## API Error Codes

Structured API errors use this schema:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "details": {},
  "request_id": "a2f9d580-4e56-4d6d-9c73-46986b8c84de"
}
```

Supported error codes:

- `VALIDATION_ERROR` — invalid input or request validation failure
- `NOT_FOUND` — requested resource does not exist
- `AUTH_FAILED` — authentication or authorization failure
- `RATE_LIMITED` — request rejected by API rate limiting
- `INTERNAL_ERROR` — unexpected server error

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
