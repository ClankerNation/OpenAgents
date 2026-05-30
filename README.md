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

## Request ID & Log Correlation

Every API response includes an `X-Request-ID` header for request tracing and log correlation.

- **Client-provided:** Pass your own ID via the `X-Request-ID` request header
- **Auto-generated:** If omitted, a UUID v4 is generated per request
- **Propagation:** The same ID is forwarded to downstream service calls
- **Structured logging:** All log entries include the request ID in `[brackets]` for correlation

### Usage

```python
from api.middleware.request_id import get_request_id

rid = get_request_id()
logger.info("Processing payment", extra={"request_id": rid})
```
