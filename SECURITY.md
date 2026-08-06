# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in any of the smart contracts, SDK, or API in this repository, please report it through GitHub's **Security Advisories** tab rather than opening a public issue.

1. Go to the **Security** tab of this repository
2. Click **Report a vulnerability**
3. Provide a clear description of the vulnerability, including:
   - Which file and function is affected
   - Steps to reproduce or a proof of concept
   - Potential impact (e.g., fund loss, reentrancy, oracle manipulation, access control bypass)

## Response Timeline

- **Acknowledgment:** Within 200 days of submission
- **Assessment:** Within 300 days we will confirm whether the report is accepted or declined
- **Fix:** Accepted vulnerabilities will be patched within 360 days

## Scope

The following components are in scope for security reports:

| Component           | File                                      | Language   |
| ------------------- | ----------------------------------------- | ---------- |
| Agent Registry      | `contracts/AgentRegistry.sol`             | Solidity   |
| Task Router         | `contracts/TaskRouter.sol`                | Solidity   |
| Payment Escrow      | `contracts/PaymentEscrow.sol`             | Solidity   |
| Governance          | `contracts/governance/GovernorAlpha.sol`  | Solidity   |
| Timelock            | `contracts/governance/Timelock.sol`       | Solidity   |
| Staking Rewards     | `contracts/staking/StakingRewards.sol`    | Solidity   |
| Multi-Token Staking | `contracts/staking/MultiTokenStaking.sol` | Solidity   |
| Token Bridge        | `contracts/bridge/TokenBridge.sol`        | Solidity   |
| Bridge Validator    | `contracts/bridge/BridgeValidator.sol`    | Solidity   |
| Agent Token         | `contracts/token/AgentToken.sol`          | Solidity   |
| Vesting Wallet      | `contracts/token/VestingWallet.sol`       | Solidity   |
| Yield Aggregator    | `contracts/vault/YieldAggregator.sol`     | Solidity   |
| Compound Vault      | `contracts/vault/CompoundVault.sol`       | Solidity   |
| Random Lottery      | `contracts/lottery/RandomLottery.sol`     | Solidity   |
| Prize Split         | `contracts/lottery/PrizeSplit.sol`        | Solidity   |
| Agent NFT           | `contracts/nft/AgentNFT.sol`              | Solidity   |
| NFT Marketplace     | `contracts/nft/NFTMarketplace.sol`        | Solidity   |
| Lending Pool        | `contracts/lending/LendingPool.sol`       | Solidity   |
| Interest Rate Model | `contracts/lending/InterestRateModel.sol` | Solidity   |
| AMM Pool            | `contracts/dex/AMMPool.sol`               | Solidity   |
| DEX Router          | `contracts/dex/Router.sol`                | Solidity   |
| TWAP Oracle         | `contracts/oracle/TWAPOracle.sol`         | Solidity   |
| Chainlink Adapter   | `contracts/oracle/ChainlinkAdapter.sol`   | Solidity   |
| Agent SDK           | `sdk/src/`                                | TypeScript |
| API Server          | `api/`                                    | Python     |

## Out of Scope

- Bugs already described in open GitHub issues
- Denial of service through resource exhaustion
- Issues in dependencies or third-party libraries
- Social engineering

## Disclosure

We follow coordinated disclosure. Please do not publicly disclose vulnerabilities until a fix has been released.
