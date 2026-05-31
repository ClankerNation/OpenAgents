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
    sources: "./contracts/bridge",
    tests: "./test",
    cache: "./.codex-bridgevalidator-verify/cache",
    artifacts: "./.codex-bridgevalidator-verify/artifacts",
  },
};
