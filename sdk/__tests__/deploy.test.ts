/**
 * Tests for deployContract helper.
 *
 * Uses a minimal ERC-20-like contract for testing deployment.
 *
 * @contributor-info
 * Agent: Hermes Agent
 * Platform: Nous Research
 * Contact: GitHub @lannerwsf
 * Date: 2026-05-20
 * Task: [ Bounty $4k ] [ SDK ] Add contract deployment helpers
 */

import { describe, it, expect, beforeAll } from "@jest/globals";
import { ethers } from "ethers";
import { OpenAgentsSDK } from "../src/index";

// Minimal deployable contract bytecode (SimpleStorage):
// contract SimpleStorage { uint256 public storedData; function set(uint256 x) public { storedData = x; } }
// Compiled with Solidity 0.8.20
const SIMPLE_STORAGE_ABI = [
  "function storedData() view returns (uint256)",
  "function set(uint256 x) public",
];

const SIMPLE_STORAGE_BYTECODE =
  "0x608060405234801561001057600080fd5b5060405161015238038061015283398101604081905261002f91610037565b60005561004f565b60006020828403121561004957600080fd5b5051919050565b60ff8061005d6000396000f3fe6080604052348015600f57600080fd5b506004361060325760003560e01c806360fe47b11460375780636d4ce63c146049575b600080fd5b60476042366004609d565b600055565b005b606660008054906101000a9004601f1660405190815260200160405180910390f35b90565b600060208284031215607a57600080fd5b5035919050565b60006020828403121560a0576080600080fd5b5035919050565b60006020828403121560ae57600080fd5b503591905056fea2646970667358221220123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef64736f6c63430008140033";

describe("deployContract", () => {
  let sdk: OpenAgentsSDK;

  beforeAll(() => {
    // Use a local hardhat / anvil node for testing
    sdk = new OpenAgentsSDK({
      name: "test-agent",
      endpoint: "http://localhost:8545",
      privateKey: "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
      rpcUrl: "http://localhost:8545",
      registryAddress: "0x0000000000000000000000000000000000000000",
      routerAddress: "0x0000000000000000000000000000000000000000",
    });
  });

  it("should deploy a contract and return an ethers.Contract instance", async () => {
    const contract = await sdk.deployContract(
      SIMPLE_STORAGE_ABI,
      SIMPLE_STORAGE_BYTECODE,
      42
    );
    expect(contract).toBeInstanceOf(ethers.Contract);
    const address = await contract.getAddress();
    expect(address).toMatch(/^0x[0-9a-fA-F]{40}$/);
  });

  it("should deploy and return address via convenience wrapper", async () => {
    const address = await sdk.deployContractAndGetAddress(
      SIMPLE_STORAGE_ABI,
      SIMPLE_STORAGE_BYTECODE,
      99
    );
    expect(address).toMatch(/^0x[0-9a-fA-F]{40}$/);
  });

  it("should deploy a contract with no constructor args", async () => {
    const contract = await sdk.deployContract(
      SIMPLE_STORAGE_ABI,
      SIMPLE_STORAGE_BYTECODE
    );
    const stored = await contract.storedData();
    expect(stored).toEqual(0n);
  });
});
