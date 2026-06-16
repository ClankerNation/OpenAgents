{
  "title": "OpenAgents",
  "subtitle": "Decentralized AI Agent Orchestration Protocol",
  "description": "OpenAgents is an open-source protocol for coordinating autonomous AI agents in decentralized environments. It provides the infrastructure for agent-to-agent communication, task delegation, and verifiable execution on-chain.",
  "architecture": {
    "diagram": "┌─────────────────────────────────────────────┐\n│              OpenAgents Protocol            │\n├──────────┬──────────┬───────────┬───────────┤\n│  Agent   │  Task    │  Verifier │  Payment  │\n│  Registry│  Router  │  Network  │  Bridge   │\n├──────────┴──────────┴───────────┴───────────┤\n│           Smart Contract Layer (EVM)         │\n├─────────────────────────────────────────────┤\n│           Agent SDK (TypeScript/Python)      │\n└─────────────────────────────────────────────┘",
    "components": [
      {
        "name": "Agent Registry",
        "description": "On-chain registry for discovering and registering AI agents"
      },
      {
        "name": "Task Router",
        "description": "Distributes tasks to appropriate agents based on capabilities"
      },
      {
        "name": "Verifier Network",
        "description": "Validates agent task execution through consensus mechanisms"
      },
      {
        "name": "Payment Bridge",
        "description": "Handles secure payments and escrow between agents and users"
      }
    ]
  },
  "components": [
    {
      "name": "contracts/",
      "description": "Solidity smart contracts for agent registry, task routing, and payment escrow",
      "security_notes": [
        "Implements reentrancy guards",
        "Uses OpenZeppelin libraries for security"
      ]
    },
    {
      "name": "sdk/",
      "description": "TypeScript SDK for building agents that interact with the protocol",
      "features": [
        "Agent lifecycle management",
        "Task subscription APIs",
        "Payment handling"
      ]
    },
    {
      "name": "api/",
      "description": "FastAPI backend for off-chain indexing and agent discovery",
      "endpoints": [
        "/agents (GET) - List registered agents",
        "/tasks (POST) - Submit new tasks",
        "/results (GET) - Query task results"
      ]
    },
    {
      "name": "oracle/",
      "description": "Price oracle and task verification infrastructure",
      "note": "Uses Chainlink for price feeds where applicable"
    }
  ],
  "quick_start": {
    "steps": [
      {
        "command": "npm install",
        "description": "Install JavaScript dependencies"
      },
      {
        "command": "npx hardhat compile",
        "description": "Compile Solidity contracts"
      },
      {
        "command": "npx hardhat test",
        "description": "Run contract test suite",
        "note": "Includes tests for donation attack mitigation"
      },
      {
        "command": "cd api && pip install -r requirements.txt && uvicorn main:app",
        "description": "Start the API server"
      }
    ],
    "prerequisites": [
      "Node.js v18+",
      "Python 3.10+",
      "Hardhat",
      "Foundry (for advanced testing)"
    ]
  },
  "security": {
    "audits": "Contracts have been audited by third-party security firms",
    "bounty": "Active $6k bounty for critical vulnerabilities",
    "known_issues": [
      {
        "issue": "Donation attack on YieldAggregator deposit",
        "status": "Patched in v2.1.0",
        "mitigation": "Added deposit caps and time locks"
      }
    ]
  },
  "contributing": {
    "link": "CONTRIBUTING.md",
    "guidelines": [
      "Follow Solidity style guide",
      "Write comprehensive tests",
      "Document all changes",
      "Reference existing issues when applicable"
    ]
  },
  "resources": {
    "documentation": "https://docs.openagents.xyz",
    "discord": "https://discord.gg/openagents",
    "github": "https://github.com/openagents/protocol"
  }
}