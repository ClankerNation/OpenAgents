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
    sources: "./contracts_relay",
    tests: "./test",
    cache: "./cache-relay",
    artifacts: "./artifacts-relay",
  },
  networks: {
    hardhat: {},
  },
};
