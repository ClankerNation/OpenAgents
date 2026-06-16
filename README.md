{
  "README": {
    "title": "# OpenAgents",
    "subtitle": "**Decentralized AI Agent Orchestration Protocol**",
    "description": "OpenAgents is an open-source protocol for coordinating autonomous AI agents in decentralized environments. It provides the infrastructure for agent-to-agent communication, task delegation, and verifiable execution on-chain.",
    "architecture": {
      "title": "## Architecture",
      "diagram": "```\n┌─────────────────────────────────────────────┐\n│              OpenAgents Protocol            │\n├──────────┬──────────┬───────────┬───────────┤\n│  Agent   │  Task    │  Verifier │  Payment  │\n│  Registry│  Router  │  Network  │  Bridge   │\n├──────────┴──────────┴───────────┴───────────┤\n│           Smart Contract Layer (EVM)         │\n├─────────────────────────────────────────────┤\n│           Agent SDK (TypeScript/Python)      │\n└─────────────────────────────────────────────┘\n```"
    },
    "components": {
      "title": "## Components",
      "items": [
        "**`contracts/`** — Solidity smart contracts for agent registry, task routing, and payment escrow",
        "**`sdk/`** — TypeScript SDK for building agents that interact with the protocol",
        "**`api/`** — FastAPI backend for off-chain indexing and agent discovery",
        "**`oracle/`** — Price oracle and task verification infrastructure"
      ]
    },
    "quickStart": {
      "title": "## Quick Start",
      "commands": [
        "```bash\n# Install dependencies\nnpm install\n```",
        "```bash\n# Compile contracts\nnpx hardhat compile\n```",
        "```bash\n# Run tests\nnpx hardhat test\n```",
        "```bash\n# Start the API server\ncd api && pip install -r requirements.txt && uvicorn main:app\n```"
      ]
    },
    "contributing": "## Contributing\n\nSee [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines."
  }
}