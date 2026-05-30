# Permit2 Integration Documentation & Gotchas

This document details the Permit2 integration architecture and complex gotchas encountered during implementation.

## Architecture Overview
The integration introduces Uniswap's Permit2 contract (`0x000000000022D473030F116dDEE9F6B43aC78BA3`) to token interaction contracts:
- `StakingRewards.sol` (`stakeWithPermit`)
- `AMMPool.sol` (`swapWithPermit`)
- `LendingPool.sol` (`depositWithPermit`)

All standard methods are retained as backwards-compatible fallbacks.

## Key Gotchas & Solutions

### 1. Mocking Permit2 on Local Hardhat Network
Permit2 relies on a canonical address. To test this locally without mainnet forking, we:
- Deployed a `MockPermit2` contract.
- Used `hardhat_setCode` to write the deployed bytecode directly into the canonical Permit2 address: `0x000000000022D473030F116dDEE9F6B43aC78BA3`.
- This maps calls to that address directly to our mock contract.

### 2. Dynamic DOMAIN_SEPARATOR Calculation
EIP-712 Domain Separators typically cache the contract address or compute it at construction time. Since `MockPermit2` is compiled and deployed at one address, but then copied to `0x000000000022D473030F116dDEE9F6B43aC78BA3`, any cached address would mismatch.
- **Solution**: The `DOMAIN_SEPARATOR` is computed dynamically during signature validation using `address(this)`, ensuring the verifying contract address resolves correctly to the canonical address.

### 3. Ethers v6 Typed Data Signing
When generating EIP-712 signatures in tests, Ethers v6 uses `signer.signTypedData(domain, types, value)`. The types struct must exactly match the standard Permit2 layout:
```javascript
const types = {
  PermitTransferFrom: [
    { name: "permitted", type: "TokenPermissions" },
    { name: "spender", type: "address" },
    { name: "nonce", type: "uint256" },
    { name: "deadline", type: "uint256" }
  ],
  TokenPermissions: [
    { name: "token", type: "address" },
    { name: "amount", type: "uint256" }
  ]
};
```
Any mismatch in field names or capitalization will result in invalid signatures.
