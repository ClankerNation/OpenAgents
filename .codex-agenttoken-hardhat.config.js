require("@nomicfoundation/hardhat-toolbox");

const chainId = Number(process.env.CODEX_AGENTTOKEN_CHAIN_ID || 31337);

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  networks: {
    hardhat: {
      chainId,
    },
  },
  paths: {
    sources: "./test",
    tests: "./test",
    cache: "./.codex-agenttoken-verify/cache",
    artifacts: "./.codex-agenttoken-verify/artifacts",
  },
};
