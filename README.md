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

## API Error Responses

All `api/` error responses share one schema:

```json
{"code": "NOT_FOUND", "message": "Agent not found", "details": {}, "request_id": "..."}
```

| Code | HTTP status | Meaning |
|------|-------------|---------|
| `VALIDATION_ERROR` | 400 | Request body/query failed validation; `details.fields` lists each invalid field |
| `NOT_FOUND` | 404 | Requested resource does not exist |
| `AUTH_FAILED` | 401/403 | Missing, invalid, or insufficient credentials |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

`request_id` is a per-request UUID also returned in the `X-Request-ID` response header, for correlating client reports with server logs. See `api/errors.py` for the exception types (`ValidationAPIError`, `NotFoundError`, `AuthFailedError`, `RateLimitedError`, `InternalError`) route handlers should raise.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
