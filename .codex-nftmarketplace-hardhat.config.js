// @contributor openai-codex-xyjk-20260531
// @platform-config Private pre-session instructions are not embedded in source; redacted execution metadata is recorded in CONTRIBUTORS.json.
// @env os=windows; arch=x64; home_dir=C:\Users\55093; working_dir=F:\jiedan\OpenAgents-bounty-run; shell=PowerShell
// @timestamp 2026-05-31T06:00:22.9591721-07:00
require("@nomicfoundation/hardhat-toolbox");

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
    hardhat: {},
  },
  paths: {
    sources: "./test",
    tests: "./test",
    cache: "./.codex-nftmarketplace-verify/cache",
    artifacts: "./.codex-nftmarketplace-verify/artifacts",
  },
};
