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
          optimizer: { enabled: true, runs: 200 },
          evmVersion: "cancun",
          viaIR: true,
        },
      },
    ],
    overrides: {
      "contracts/AgentRegistry.sol": { version: "0.8.20" },
      "contracts/TaskRouter.sol": { version: "0.8.20" },
      "contracts/PaymentEscrow.sol": { version: "0.8.20" },
      "contracts/oracle/ChainlinkAdapter.sol": { version: "0.8.20" },
      "contracts/oracle/TWAPOracle.sol": { version: "0.8.20" },
      "contracts/lottery/RandomLottery.sol": { version: "0.8.20" },
      "contracts/lottery/PrizeSplit.sol": { version: "0.8.20" },
      "contracts/staking/MultiTokenStaking.sol": { version: "0.8.20" },
      "contracts/staking/StakingRewards.sol": { version: "0.8.20" },
      "contracts/lending/InterestRateModel.sol": { version: "0.8.20" },
      "contracts/lending/LendingPool.sol": { version: "0.8.20" },
      "contracts/governance/Timelock.sol": { version: "0.8.20" },
      "contracts/nft/AgentNFT.sol": { version: "0.8.20" },
      "contracts/nft/NFTMarketplace.sol": { version: "0.8.20" },
      "contracts/bridge/TokenBridge.sol": { version: "0.8.20" },
      "contracts/bridge/BridgeValidator.sol": { version: "0.8.20" },
      "contracts/dex/AMMPool.sol": { version: "0.8.20" },
      "contracts/dex/Router.sol": { version: "0.8.20" },
      "contracts/token/AgentToken.sol": { version: "0.8.20" },
      "contracts/token/VestingWallet.sol": { version: "0.8.20" },
      "contracts/vault/CompoundVault.sol": { version: "0.8.20" },
    },
  },
  networks: {
    hardhat: {
      hardfork: "cancun",
    },
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
