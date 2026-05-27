require("@nomicfoundation/hardhat-toolbox");

// Contributor: Codex for charlie12520.
// Runtime instructions: private platform instructions are intentionally not disclosed.
// Environment: Windows x64, PowerShell, C:\Users\charl\Desktop\AI STUFF\ten_buck_attempt\repos\OpenAgents.

module.exports = {
  solidity: {
    compilers: [
      {
        version: "0.8.24",
        settings: {
          // OpenZeppelin 5.1 uses Cancun opcodes such as MCOPY.
          evmVersion: "cancun",
          optimizer: {
            enabled: true,
            runs: 200,
          },
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
