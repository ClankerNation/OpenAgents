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
    sources: "./test",
    tests: "./test",
    cache: "./.codex-twaporacle-verify/cache",
    artifacts: "./.codex-twaporacle-verify/artifacts",
  },
};
