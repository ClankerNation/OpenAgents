# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-05-30

### Added
- Permit2 integration across all token interaction contracts (`StakingRewards.sol`, `AMMPool.sol`, and `LendingPool.sol`) using canonical address `0x000000000022D473030F116dDEE9F6B43aC78BA3`.
- New signature-based staking (`stakeWithPermit`), swapping (`swapWithPermit`), and deposit (`depositWithPermit`) functions.
- Fully backward-compatible fallback mechanism utilizing standard `transferFrom` (or approve flow) if Permit2 signature is not provided or standard execution is preferred.
- MockPermit2 and MockPriceFeed contract implementations for Hardhat integration tests.
- Comprehensive integration tests in `test/Permit2Integration.test.js` validating signature recovery and fallback execution paths.
