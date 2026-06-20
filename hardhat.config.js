// @contributor: Claude Code (Claude Opus 4.7)
// @platform-config: Task: Configure Hardhat for multi-compiler support for MultiTokenStaking emergencyWithdraw project. Rules: Add multi-compiler, configure optimizer. Tools: npx hardhat, npm. Style: JS/Node conventions.
// @env: os=linux, arch=x86_64, home_dir=/home/michael, working_dir=/home/michael/web3-community/OpenAgents, shell=bash
// @timestamp: 2026-06-20T08:00:00Z
require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: {
    compilers: [
      {
        version: "0.8.20",
        settings: {
          optimizer: { enabled: true, runs: 200 },
        },
      },
      {
        version: "0.8.24",
        settings: {
          evmVersion: "cancun",
          viaIR: true,
          optimizer: { enabled: true, runs: 200 },
        },
      },
    ],
  },
  networks: {
    hardhat: {},
    sepolia: {
      url: process.env.SEPOLIA_RPC_URL || "",
      accounts: process.env.DEPLOYER_KEY ? [process.env.DEPLOYER_KEY] : [],
    },
    base: {
      url: process.env.BASE_RPC_URL || "https://mainnet.base.org",
      accounts: process.env.DEPLOYER_KEY ? [process.env.DEPLOYER_KEY] : [],
    },
  },
};
