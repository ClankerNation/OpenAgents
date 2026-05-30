/**
 * @fix-author kejuunuy
 * Tests for contract deployment helpers.
 */

import { ethers } from "ethers";
import { deployContract, estimateDeployGas, DeployContractOptions, DeploymentResult } from "../src/deploy/contract";
import { OpenAgentsSDK } from "../src/index";

// Minimal valid contract bytecode (simplest possible - PUSH0 + REVERT)
const MINIMAL_BYTECODE = "0x6080604052600080fdfea164736f6c6343000814000a";

const SIMPLE_ABI = ["constructor()"];
const ABI_WITH_ARGS = ["constructor(address owner, uint256 supply)"];

const TEST_ADDRESS = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"; // valid lowercase

// --- Mock Provider and Signer ---

function createMockProvider() {
  return {
    getFeeData: async () => ({
      gasPrice: 20_000_000_000n,
      maxFeePerGas: null,
      maxPriorityFeePerGas: null,
    }),
    getNetwork: async () => ({ chainId: 1n, name: "mainnet" }),
    getBlockNumber: async () => 12345,
    estimateGas: async () => 50000n,
    resolveName: async (name: string) => name, // ENS passthrough
  };
}

function createMockSigner(providerOverride?: any) {
  const provider = providerOverride ?? createMockProvider();
  let lastTx: any = null;

  const signer: any = {
    provider,
    address: "0x1234567890abcdef1234567890abcdef12345678",
    estimateGas: async (tx: any) => {
      return 50000n;
    },
    sendTransaction: async (tx: any) => {
      lastTx = tx;
      return {
        hash: "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
        wait: async (confirmations?: number) => ({
          contractAddress: "0x9876543210fedcba9876543210fedcba98765432",
          hash: "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
          blockNumber: 12346,
          gasPrice: 20_000_000_000n,
          status: 1,
        }),
      };
    },
  };

  return { signer, getLastTx: () => lastTx };
}

// --- Test Helpers ---

let passed = 0;
let failed = 0;
const errors: string[] = [];

function assert(condition: boolean, message: string) {
  if (condition) {
    passed++;
    console.log(`  ✅ ${message}`);
  } else {
    failed++;
    errors.push(message);
    console.log(`  ❌ ${message}`);
  }
}

function assertEqual(actual: any, expected: any, message: string) {
  assert(actual === expected, `${message} (got: ${actual}, expected: ${expected})`);
}

async function assertThrows(fn: () => Promise<any>, expectedMsg: string, testName: string) {
  try {
    await fn();
    failed++;
    errors.push(`${testName}: expected to throw but did not`);
    console.log(`  ❌ ${testName}: expected to throw but did not`);
  } catch (err: any) {
    if (err.message.includes(expectedMsg)) {
      passed++;
      console.log(`  ✅ ${testName}: threw expected error`);
    } else {
      failed++;
      errors.push(`${testName}: wrong error message: ${err.message}`);
      console.log(`  ❌ ${testName}: wrong error: ${err.message}`);
    }
  }
}

// --- Tests ---

async function testEstimateDeployGas() {
  console.log("\n📦 estimateDeployGas");

  const { signer } = createMockSigner();

  // Test basic estimation
  const gas = await estimateDeployGas(
    signer as any,
    MINIMAL_BYTECODE,
    SIMPLE_ABI,
    [],
    0n
  );
  assert(typeof gas === "bigint", "returns a bigint");
  assert(gas > 0n, "gas estimate is positive");
  assertEqual(gas, 60000n, "includes 20% buffer");

  // Test with constructor args
  const gasWithArgs = await estimateDeployGas(
    signer as any,
    MINIMAL_BYTECODE,
    ABI_WITH_ARGS,
    [TEST_ADDRESS, 1000000],
    0n
  );
  assert(gasWithArgs > 0n, "estimates gas with constructor args");

  // Test with value
  const gasWithValue = await estimateDeployGas(
    signer as any,
    MINIMAL_BYTECODE,
    SIMPLE_ABI,
    [],
    ethers.parseEther("1.0")
  );
  assert(gasWithValue > 0n, "estimates gas with value");
}

async function testDeployContractSuccess() {
  console.log("\n📦 deployContract — success cases");

  const { signer } = createMockSigner();

  // Basic deployment
  const result = await deployContract(signer as any, {
    bytecode: MINIMAL_BYTECODE,
    abi: SIMPLE_ABI,
  });

  assert(typeof result.contractAddress === "string", "returns contract address");
  assert(result.contractAddress.startsWith("0x"), "address starts with 0x");
  assert(result.contractAddress.length === 42, "address is 42 chars");
  assert(typeof result.transactionHash === "string", "returns transaction hash");
  assert(typeof result.blockNumber === "number", "returns block number");
  assert(result.blockNumber > 0, "block number is positive");
  assert(typeof result.gasUsed === "bigint", "returns gasUsed as bigint");
  assert(typeof result.effectiveGasPrice === "bigint", "returns effectiveGasPrice as bigint");
  assert(result.receipt !== null && result.receipt !== undefined, "includes receipt");
  assert(result.contract !== null && result.contract !== undefined, "includes contract instance");

  // With constructor args
  const resultWithArgs = await deployContract(signer as any, {
    bytecode: MINIMAL_BYTECODE,
    abi: ABI_WITH_ARGS,
    constructorArgs: [TEST_ADDRESS, 1000000],
  });
  assert(resultWithArgs.contractAddress.startsWith("0x"), "deploys with constructor args");

  // With custom gas limit
  const resultCustomGas = await deployContract(signer as any, {
    bytecode: MINIMAL_BYTECODE,
    abi: SIMPLE_ABI,
    gasLimit: 100000n,
  });
  assert(resultCustomGas.contractAddress.startsWith("0x"), "deploys with custom gas limit");

  // With custom gas price
  const resultGasPrice = await deployContract(signer as any, {
    bytecode: MINIMAL_BYTECODE,
    abi: SIMPLE_ABI,
    gasPrice: 30_000_000_000n,
  });
  assert(resultGasPrice.contractAddress.startsWith("0x"), "deploys with custom gas price");

  // With value
  const resultValue = await deployContract(signer as any, {
    bytecode: MINIMAL_BYTECODE,
    abi: SIMPLE_ABI,
    value: ethers.parseEther("0.5"),
  });
  assert(resultValue.contractAddress.startsWith("0x"), "deploys with value");

  // With custom confirmations
  const resultConfirmations = await deployContract(signer as any, {
    bytecode: MINIMAL_BYTECODE,
    abi: SIMPLE_ABI,
    confirmations: 3,
  });
  assert(resultConfirmations.contractAddress.startsWith("0x"), "deploys with custom confirmations");
}

async function testDeployContractErrors() {
  console.log("\n📦 deployContract — error cases");

  const { signer } = createMockSigner();

  // Empty bytecode
  await assertThrows(
    () => deployContract(signer as any, { bytecode: "0x", abi: SIMPLE_ABI }),
    "bytecode is empty",
    "rejects empty bytecode"
  );

  await assertThrows(
    () => deployContract(signer as any, { bytecode: "", abi: SIMPLE_ABI }),
    "bytecode is empty",
    "rejects empty string bytecode"
  );
}

async function testDeployContractRevert() {
  console.log("\n📦 deployContract — reverted transaction");

  const provider = createMockProvider();
  const signer: any = {
    provider,
    address: "0x1234567890abcdef1234567890abcdef12345678",
    estimateGas: async () => 50000n,
    sendTransaction: async () => ({
      hash: "0xdeadbeef",
      wait: async () => ({
        contractAddress: "0x9876543210fedcba9876543210fedcba98765432",
        hash: "0xdeadbeef",
        blockNumber: 12346,
        gasPrice: 20_000_000_000n,
        status: 0, // reverted
      }),
    }),
  };

  await assertThrows(
    () => deployContract(signer, { bytecode: MINIMAL_BYTECODE, abi: SIMPLE_ABI }),
    "transaction reverted",
    "rejects reverted deployment"
  );
}

async function testDeployContractTimeout() {
  console.log("\n📦 deployContract — timeout");

  const provider = createMockProvider();
  const signer: any = {
    provider,
    address: "0x1234567890abcdef1234567890abcdef12345678",
    estimateGas: async () => 50000n,
    sendTransaction: async () => ({
      hash: "0xtimeout",
      wait: async () => new Promise((resolve) => setTimeout(resolve, 10000)),
    }),
  };

  await assertThrows(
    () =>
      deployContract(signer, {
        bytecode: MINIMAL_BYTECODE,
        abi: SIMPLE_ABI,
        timeout: 100,
      }),
    "timed out",
    "times out when deployment takes too long"
  );
}

async function testDeployContractNoReceipt() {
  console.log("\n📦 deployContract — null receipt");

  const provider = createMockProvider();
  const signer: any = {
    provider,
    address: "0x1234567890abcdef1234567890abcdef12345678",
    estimateGas: async () => 50000n,
    sendTransaction: async () => ({
      hash: "0xnoreceipt",
      wait: async () => null,
    }),
  };

  await assertThrows(
    () => deployContract(signer, { bytecode: MINIMAL_BYTECODE, abi: SIMPLE_ABI }),
    "no receipt",
    "handles null receipt"
  );
}

async function testSDKDeployMethod() {
  console.log("\n📦 OpenAgentsSDK.deployContract");

  assert(
    typeof OpenAgentsSDK.prototype.deployContract === "function",
    "OpenAgentsSDK has deployContract method"
  );
}

async function testGasEstimationBuffer() {
  console.log("\n📦 Gas estimation buffer calculation");

  const provider = createMockProvider();
  const signer: any = {
    provider,
    address: "0xtest",
    estimateGas: async () => 100000n,
  };

  const gas = await estimateDeployGas(signer, MINIMAL_BYTECODE, SIMPLE_ABI);
  assertEqual(gas, 120000n, "applies 20% buffer (100000 * 1.2 = 120000)");
}

async function testCustomGasOverridesEstimate() {
  console.log("\n📦 Custom gas limit skips estimation");

  let estimateCalled = false;
  const provider = createMockProvider();
  const signer: any = {
    provider,
    address: "0x1234567890abcdef1234567890abcdef12345678",
    estimateGas: async () => {
      estimateCalled = true;
      return 50000n;
    },
    sendTransaction: async (tx: any) => {
      assertEqual(tx.gasLimit, 999999n, "uses custom gas limit instead of estimation");
      return {
        hash: "0xcustomgas",
        wait: async () => ({
          contractAddress: "0x9876543210fedcba9876543210fedcba98765432",
          hash: "0xcustomgas",
          blockNumber: 100,
          gasPrice: 20_000_000_000n,
          status: 1,
        }),
      };
    },
  };

  await deployContract(signer, {
    bytecode: MINIMAL_BYTECODE,
    abi: SIMPLE_ABI,
    gasLimit: 999999n,
  });

  assert(!estimateCalled, "skips gas estimation when gasLimit is provided");
}

// --- Main ---

async function main() {
  console.log("🧪 Contract Deployment Helpers — Test Suite\n");

  try {
    await testEstimateDeployGas();
    await testDeployContractSuccess();
    await testDeployContractErrors();
    await testDeployContractRevert();
    await testDeployContractTimeout();
    await testDeployContractNoReceipt();
    await testSDKDeployMethod();
    await testGasEstimationBuffer();
    await testCustomGasOverridesEstimate();
  } catch (err) {
    console.error("\n💥 Unexpected error:", err);
    failed++;
  }

  console.log(`\n${"─".repeat(50)}`);
  console.log(`Results: ${passed} passed, ${failed} failed`);
  if (errors.length > 0) {
    console.log("\nFailed tests:");
    errors.forEach((e) => console.log(`  - ${e}`));
  }
  console.log(`${"─".repeat(50)}\n`);

  process.exit(failed > 0 ? 1 : 0);
}

main();
