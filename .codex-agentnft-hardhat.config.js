require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  paths: {
    sources: "./contracts/nft",
    tests: "./test",
    cache: "./.codex-agentnft-verify/cache",
    artifacts: "./.codex-agentnft-verify/artifacts",
  },
};
