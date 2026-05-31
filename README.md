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

## API Error Response Schema

API errors follow a structured schema:

```json
{
  "code": "NOT_FOUND",
  "message": "Agent not found",
  "details": {},
  "request_id": "b7493a68-3b97-4404-87e0-4cad36b19ca1"
}
```

Error codes:

- `VALIDATION_ERROR` - Request validation failed
- `NOT_FOUND` - Resource not found
- `AUTH_FAILED` - Authentication or authorization failed
- `RATE_LIMITED` - Rate limit exceeded
- `INTERNAL_ERROR` - Unhandled server-side failure

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
