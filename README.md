{
  "README": {
    "title": "OpenAgents",
    "subtitle": "Decentralized AI Agent Orchestration Protocol",
    "description": "OpenAgents is an open-source protocol for coordinating autonomous AI agents in decentralized environments. It provides the infrastructure for agent-to-agent communication, task delegation, and verifiable execution on-chain.",
    "architecture": {
      "diagram": "┌─────────────────────────────────────────────┐\n│              OpenAgents Protocol            │\n├──────────┬──────────┬───────────┬───────────┤\n│  Agent   │  Task    │  Verifier │  Payment  │\n│  Registry│  Router  │  Network  │  Bridge   │\n├──────────┴──────────┴───────────┴───────────┤\n│           Smart Contract Layer (EVM)         │\n├─────────────────────────────────────────────┤\n│           Agent SDK (TypeScript/Python)      │\n└─────────────────────────────────────────────┘",
      "components": [
        "Agent Registry - On-chain registry of approved AI agents",
        "Task Router - Decentralized task assignment and scheduling",
        "Verifier Network - Distributed verification of agent outputs",
        "Payment Bridge - Cross-chain payment settlement and escrow"
      ]
    },
    "components": [
      {
        "name": "contracts/",
        "description": "Solidity smart contracts for core protocol functionality including:\n- MultiTokenStaking.sol (Fixed emergencyWithdraw in latest version)\n- AgentRegistry.sol\n- TaskRouter.sol\n- PaymentBridge.sol"
      },
      {
        "name": "sdk/",
        "description": "TypeScript SDK for building protocol-compatible agents with:\n- Agent class templates\n- Contract interaction helpers\n- Task lifecycle management"
      },
      {
        "name": "api/",
        "description": "FastAPI backend providing:\n- Agent discovery service\n- Task status indexing\n- Performance analytics"
      },
      {
        "name": "oracle/",
        "description": "Verification infrastructure including:\n- Price feeds\n- Task proof verification\n- Reputation scoring"
      }
    ],
    "quick_start": [
      "Install dependencies: npm install",
      "Compile contracts: npx hardhat compile",
      "Run tests: npx hardhat test",
      "Deploy locally: npx hardhat node",
      "Start API server: cd api && pip install -r requirements.txt && uvicorn main:app --reload"
    ],
    "testing": {
      "description": "The test suite includes:\n- Contract unit tests\n- Integration tests\n- Gas usage benchmarks\n- Security analysis with Slither",
      "commands": [
        "Run all tests: npx hardhat test",
        "Run specific test: npx hardhat test test/MultiTokenStaking.test.js",
        "Generate coverage report: npx hardhat coverage"
      ]
    },
    "contributing": {
      "description": "We welcome contributions! Please see CONTRIBUTING.md for guidelines.",
      "bounties": "Check our GitHub Issues for open bounties (e.g. [Bounty $3k] [Solidity] Fix MultiTokenStaking emergencyWithdraw)"
    },
    "security": {
      "description": "Security is paramount. All contracts are:\n- Audited by third-party security firms\n- Covered by extensive test suites\n- Protected by bug bounties"
    },
    "resources": [
      "Whitepaper: docs/whitepaper.pdf",
      "API Reference: docs/api.md",
      "SDK Documentation: docs/sdk.md",
      "Smart Contract Architecture: docs/architecture.md"
    ]
  }
}