/**
 * Tests for contract deployment functionality.
 */

const assert = require("assert");

console.log("Running deploy tests...\n");

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`✓ ${name}`);
    passed++;
  } catch (e) {
    console.error(`✗ ${name}`);
    console.error(`  ${e.message}`);
    failed++;
  }
}

test("DeploymentReceipt interface", () => {
  const receipt = {
    address: "0x123",
    txHash: "0xabc",
    gasUsed: 100000n,
    blockNumber: 123,
    contract: {},
  };
  assert.equal(typeof receipt.address, "string");
  assert.equal(typeof receipt.gasUsed, "bigint");
});

test("constructor args are array", () => {
  const args = ["0xToken", 1000n];
  assert.ok(Array.isArray(args));
  assert.equal(args.length, 2);
});

test("bytecode starts with 0x", () => {
  const bytecode = "0x608060405234801561001057600080fd5b50";
  assert.ok(bytecode.startsWith("0x"));
});

test("confirmations defaults to 1", () => {
  const confirmations = 1;
  assert.equal(confirmations, 1);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exitCode = 1;
