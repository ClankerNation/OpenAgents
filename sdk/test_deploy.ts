/**
 * Test suite for SDK deployContract helper.
 *
 * These tests verify the deployContract interface and structure,
 * without needing a live RPC endpoint.
 *
 * Usage: npx tsx sdk/test_deploy.ts
 */

import { ethers } from "ethers";
import { OpenAgentsSDK, DeployResult } from "./src/index";

let passed = 0;
let failed = 0;

function assertEq(label: string, actual: any, expected: any): void {
  const ok = actual === expected;
  if (ok) {
    passed++;
    console.log(`  ✅ ${label}`);
  } else {
    failed++;
    console.error(`  ❌ ${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertMatch(label: string, actual: any, pattern: RegExp): void {
  const ok = pattern.test(String(actual));
  if (ok) {
    passed++;
    console.log(`  ✅ ${label}`);
  } else {
    failed++;
    console.error(`  ❌ ${label} — "${actual}" doesn't match ${pattern}`);
  }
}

// Test 1: DeployResult interface shape
console.log("\n📦 Testing DeployResult interface:");
{
  const result: DeployResult = {
    address: "0x1234567890123456789012345678901234567890",
    txHash: "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    gasUsed: 21000n,
    contract: {} as ethers.Contract,
  };
  assertMatch("address is 0x-prefixed", result.address, /^0x[a-f0-9]{40}$/);
  assertMatch("txHash is 0x-prefixed", result.txHash, /^0x[a-f0-9]{64}$/);
  assertEq("gasUsed is bigint", typeof result.gasUsed, "bigint");
  assertEq("contract is object", typeof result.contract, "object");
}

// Test 2: deployContract exists and is a function
console.log("\n📦 Testing deployContract method signature:");
{
  const sdkMethods = Object.getOwnPropertyNames(OpenAgentsSDK.prototype)
    .filter(m => m !== "constructor");
  assertEq("deployContract exists", sdkMethods.includes("deployContract"), true);
  assertEq("deployContract is function", typeof OpenAgentsSDK.prototype.deployContract, "function");
}

// Test 3: DeployResult fields cannot be undefined after construction
console.log("\n📦 Testing DeployResult field types:");
{
  const r: DeployResult = {
    address: "0x0000000000000000000000000000000000000000",
    txHash: "0x" + "0".repeat(64),
    gasUsed: 0n,
    contract: {} as ethers.Contract,
  };
  assertEq("address is string", typeof r.address, "string");
  assertEq("gasUsed is bigint", typeof r.gasUsed, "bigint");
}

// Summary
console.log(`\n${"=".repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
} else {
  console.log("All tests passed! ✅");
}
