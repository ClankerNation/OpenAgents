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

## API Error Format

All API errors follow a consistent structured format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": {}
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid request parameters |
| `AUTH_ERROR` | 401 | Authentication failure |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMIT` | 429 | Rate limit exceeded |
| `CONFLICT` | 409 | Resource conflict |
| `INTERNAL_ERROR` | 500 | Unexpected server error |
| `INVALID_INPUT` | 400 | Invalid input data |
| `DUPLICATE_ENTRY` | 409 | Duplicate resource |
| `PAYMENT_ERROR` | 400 | Payment processing error |
| `TASK_ERROR` | 400 | Task state error |
| `AGENT_ERROR` | 400 | Agent operation error |
