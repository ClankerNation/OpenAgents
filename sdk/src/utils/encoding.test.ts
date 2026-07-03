/**
 * Tests for encoding.ts — ABI encoding/decoding utilities.
 *
 * Run with: npx tsx sdk/src/utils/encoding.test.ts
 *
 * @fix-author hermes-agent
 * @fix-description Tests for decodeParameter dynamic type support
 * @fix-issue #198
 */

import {
  decodeParameter,
  decodeUint256,
  decodeAddress,
  decodeBool,
  decodeHex,
  parseTupleTypes,
} from "./encoding";

// ---------------------------------------------------------------------------
// Simple test harness (matches retry.test.ts pattern)
// ---------------------------------------------------------------------------
let testsRun = 0;
let testsPassed = 0;

function assert(condition: boolean, msg: string): void {
  testsRun++;
  if (condition) {
    testsPassed++;
    console.log(`  ✓ ${msg}`);
  } else {
    console.error(`  ✗ FAIL: ${msg}`);
  }
}

function bigintReplacer(_key: string, value: unknown): unknown {
  return typeof value === "bigint" ? value.toString() + "n" : value;
}

function assertDeepEqual(actual: unknown, expected: unknown, msg: string): void {
  testsRun++;
  const a = JSON.stringify(actual, bigintReplacer);
  const e = JSON.stringify(expected, bigintReplacer);
  if (a === e) {
    testsPassed++;
    console.log(`  ✓ ${msg}`);
  } else {
    console.error(`  ✗ FAIL: ${msg} — expected ${e}, got ${a}`);
  }
}

// ============================================================
// Test Suites
// ============================================================

// ---------------------------------------------------------------------------
// decodeUint256
// ---------------------------------------------------------------------------
function testDecodeUint256() {
  console.log("\n--- decodeUint256 ---");
  assert(decodeUint256("000000000000000000000000000000000000000000000000000000000000002a") === 42n, "standard 64-char slot → 42");
  assert(decodeUint256("2a") === 42n, "short unpadded slot → 42");
  assert(decodeUint256("0".repeat(64)) === 0n, "zeros → 0");
  const max = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";
  assert(decodeUint256(max) === 2n ** 256n - 1n, "max uint256");
}

// ---------------------------------------------------------------------------
// decodeAddress
// ---------------------------------------------------------------------------
function testDecodeAddress() {
  console.log("\n--- decodeAddress ---");
  const addr = decodeAddress("000000000000000000000000ab5801a7d398351b8be11c439e05c5b3259aec9b");
  assert(addr === "0xab5801a7d398351b8be11c439e05c5b3259aec9b", "extracts last 40 hex chars");
}

// ---------------------------------------------------------------------------
// decodeBool
// ---------------------------------------------------------------------------
function testDecodeBool() {
  console.log("\n--- decodeBool ---");
  assert(decodeBool("0000000000000000000000000000000000000000000000000000000000000001") === true, "non-zero → true");
  assert(decodeBool("0000000000000000000000000000000000000000000000000000000000000000") === false, "zero → false");
}

// ---------------------------------------------------------------------------
// decodeHex
// ---------------------------------------------------------------------------
function testDecodeHex() {
  console.log("\n--- decodeHex ---");
  assert(decodeHex("0x2a") === 42n, "with 0x prefix");
  assert(decodeHex("2a") === 42n, "without prefix");
}

// ---------------------------------------------------------------------------
// parseTupleTypes
// ---------------------------------------------------------------------------
function testParseTupleTypes() {
  console.log("\n--- parseTupleTypes ---");
  assertDeepEqual(parseTupleTypes("uint256,address,bool"), ["uint256", "address", "bool"], "simple types");
  assertDeepEqual(parseTupleTypes("uint256,(address,string)"), ["uint256", "(address,string)"], "nested tuple");
  assertDeepEqual(parseTupleTypes("address[],uint256[]"), ["address[]", "uint256[]"], "array types");
}

// ---------------------------------------------------------------------------
// decodeParameter — Static types
// ---------------------------------------------------------------------------
function testDecodeParameterStatic() {
  console.log("\n--- decodeParameter: static types ---");
  const data =
    "000000000000000000000000000000000000000000000000000000000000002a" +
    "000000000000000000000000ab5801a7d398351b8be11c439e05c5b3259aec9b" +
    "0000000000000000000000000000000000000000000000000000000000000001" +
    "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef";

  assert(decodeParameter("uint256", data, 0) === 42n, "uint256 at offset 0");
  assert(
    decodeParameter("address", data, 32) === "0xab5801a7d398351b8be11c439e05c5b3259aec9b",
    "address at offset 32",
  );
  assert(decodeParameter("bool", data, 64) === true, "bool at offset 64");
  assert(
    decodeParameter("bytes32", data, 96) === "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "bytes32 at offset 96",
  );
}

// ---------------------------------------------------------------------------
// decodeParameter — String
// ---------------------------------------------------------------------------
function testDecodeParameterString() {
  console.log("\n--- decodeParameter: string ---");

  // "Hello, World!" (13 chars)
  const helloHex =
    "48656c6c6f2c20576f726c642100000000000000000000000000000000000000";
  const data =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "000000000000000000000000000000000000000000000000000000000000000d" +
    helloHex;

  assert(decodeParameter("string", data, 0) === "Hello, World!", "simple string");

  // Empty string
  const emptyData =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000000";
  assert(decodeParameter("string", emptyData, 0) === "", "empty string");

  // Multi-byte UTF-8: "Hello 🌍" (10 bytes)
  const utf8Hex =
    "48656c6c6f20f09f8c8d00000000000000000000000000000000000000000000";
  const utf8Data =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "000000000000000000000000000000000000000000000000000000000000000a" +
    utf8Hex;
  assert(decodeParameter("string", utf8Data, 0) === "Hello 🌍", "UTF-8 string with emoji");
}

// ---------------------------------------------------------------------------
// decodeParameter — bytes
// ---------------------------------------------------------------------------
function testDecodeParameterBytes() {
  console.log("\n--- decodeParameter: bytes ---");

  // 0xdeadbeef (4 bytes)
  const bytesHex =
    "deadbeef0000000000000000000000000000000000000000000000000000000000";
  const data =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000004" +
    bytesHex;
  assert(decodeParameter("bytes", data, 0) === "0xdeadbeef", "dynamic bytes");

  // Empty bytes
  const emptyData =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000000";
  assert(decodeParameter("bytes", emptyData, 0) === "0x", "empty bytes");
}

// ---------------------------------------------------------------------------
// decodeParameter — Dynamic arrays
// ---------------------------------------------------------------------------
function testDecodeParameterArrays() {
  console.log("\n--- decodeParameter: dynamic arrays ---");

  // uint256[] = [1, 2, 3]
  const data =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000003" +
    "0000000000000000000000000000000000000000000000000000000000000001" +
    "0000000000000000000000000000000000000000000000000000000000000002" +
    "0000000000000000000000000000000000000000000000000000000000000003";
  assertDeepEqual(decodeParameter("uint256[]", data, 0), [1n, 2n, 3n], "uint256[] = [1,2,3]");

  // address[] = [0xab58..., 0xdead]
  const addrData =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000002" +
    "000000000000000000000000ab5801a7d398351b8be11c439e05c5b3259aec9b" +
    "000000000000000000000000000000000000000000000000000000000000dead";
  const addrResult = decodeParameter("address[]", addrData, 0);
  assert(addrResult.length === 2, "address[] length === 2");
  assert(addrResult[0] === "0xab5801a7d398351b8be11c439e05c5b3259aec9b", "address[0]");
  assert(addrResult[1] === "0x000000000000000000000000000000000000dead", "address[1]");

  // Empty array
  const emptyArr =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000000";
  assertDeepEqual(decodeParameter("uint256[]", emptyArr, 0), [], "empty uint256[]");
}

// ---------------------------------------------------------------------------
// decodeParameter — Tuples
// ---------------------------------------------------------------------------
function testDecodeParameterTuples() {
  console.log("\n--- decodeParameter: tuples ---");

  // Static tuple: (uint256, address, bool)
  const staticTuple =
    "000000000000000000000000000000000000000000000000000000000000002a" +
    "000000000000000000000000ab5801a7d398351b8be11c439e05c5b3259aec9b" +
    "0000000000000000000000000000000000000000000000000000000000000001";
  const staticResult = decodeParameter("(uint256,address,bool)", staticTuple, 0);
  assert(staticResult.length === 3, "tuple length === 3");
  assert(staticResult[0] === 42n, "tuple[0] = 42");
  assert(staticResult[1] === "0xab5801a7d398351b8be11c439e05c5b3259aec9b", "tuple[1] = address");
  assert(staticResult[2] === true, "tuple[2] = true");

  // Dynamic tuple: (string, uint256) = ("hello", 42) as single return value
  // offset 0: pointer to tuple = 0x20 = 32
  // offset 32: tuple head — string pointer (rel to tuple start) = 0x40 = 64
  // offset 64: tuple head — uint256 = 42
  // offset 96: tuple tail — string length = 5
  // offset 128: tuple tail — "hello"
  const dynamicTuple =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000040" +
    "000000000000000000000000000000000000000000000000000000000000002a" +
    "0000000000000000000000000000000000000000000000000000000000000005" +
    "68656c6c6f000000000000000000000000000000000000000000000000000000";
  const dynamicResult = decodeParameter("(string,uint256)", dynamicTuple, 0);
  assert(dynamicResult.length === 2, "dynamic tuple length === 2");
  assert(dynamicResult[0] === "hello", 'dynamic tuple[0] = "hello"');
  assert(dynamicResult[1] === 42n, "dynamic tuple[1] = 42");
}

// ---------------------------------------------------------------------------
// decodeParameter — Complex: array of tuples
// ---------------------------------------------------------------------------
function testDecodeParameterArrayOfTuples() {
  console.log("\n--- decodeParameter: array of tuples ---");

  // (uint256,string)[] = [(1, "a"), (2, "b")]
  // Dynamic array of dynamic tuples uses head/tail encoding:
  // Head: [length][ptr to elem 0][ptr to elem 1]
  // Tail: [elem 0][elem 1]
  const data =
    "0000000000000000000000000000000000000000000000000000000000000020" +  // [0] ptr to array = 32
    "0000000000000000000000000000000000000000000000000000000000000002" +  // [32] length = 2
    "0000000000000000000000000000000000000000000000000000000000000060" +  // [64] ptr elem 0 = 96 (rel to array start=32, abs=128)
    "00000000000000000000000000000000000000000000000000000000000000e0" +  // [96] ptr elem 1 = 224 (rel to array start=32, abs=256)
    "0000000000000000000000000000000000000000000000000000000000000001" +  // [128] tuple 0: uint256 = 1
    "0000000000000000000000000000000000000000000000000000000000000040" +  // [160] tuple 0: string ptr = 64 (rel to tuple 0 start=128)
    "0000000000000000000000000000000000000000000000000000000000000001" +  // [192] tuple 0: length = 1
    "6100000000000000000000000000000000000000000000000000000000000000" +  // [224] tuple 0: "a"
    "0000000000000000000000000000000000000000000000000000000000000002" +  // [256] tuple 1: uint256 = 2
    "0000000000000000000000000000000000000000000000000000000000000040" +  // [288] tuple 1: string ptr = 64 (rel to tuple 1 start=256)
    "0000000000000000000000000000000000000000000000000000000000000001" +  // [320] tuple 1: length = 1
    "6200000000000000000000000000000000000000000000000000000000000000";  // [352] tuple 1: "b"
  const result = decodeParameter("(uint256,string)[]", data, 0);
  assert(result.length === 2, "array length === 2");
  assert(result[0].length === 2, "tuple[0] length === 2");
  assert(result[0][0] === 1n, "tuple[0][0] === 1");
  assert(result[0][1] === "a", 'tuple[0][1] === "a"');
  assert(result[1][0] === 2n, "tuple[1][0] === 2");
  assert(result[1][1] === "b", 'tuple[1][1] === "b"');
}

// ---------------------------------------------------------------------------
// decodeParameter — Multiple return values
// ---------------------------------------------------------------------------
function testDecodeParameterMultipleReturns() {
  console.log("\n--- decodeParameter: multiple return values ---");

  // Simulating a function returning (uint256, string, address)
  const data =
    "000000000000000000000000000000000000000000000000000000000000002a" +
    "0000000000000000000000000000000000000000000000000000000000000060" +
    "000000000000000000000000ab5801a7d398351b8be11c439e05c5b3259aec9b" +
    "0000000000000000000000000000000000000000000000000000000000000005" +
    "68656c6c6f000000000000000000000000000000000000000000000000000000";

  const uint256Val = decodeParameter("uint256", data, 0);
  const stringVal = decodeParameter("string", data, 32);
  const addressVal = decodeParameter("address", data, 64);

  assert(uint256Val === 42n, "uint256 return = 42");
  assert(stringVal === "hello", 'string return = "hello"');
  assert(addressVal === "0xab5801a7d398351b8be11c439e05c5b3259aec9b", "address return");
}

// ============================================================
// Run all tests
// ============================================================
async function main() {
  console.log("=== encoding.ts Test Suite ===");
  console.log(`Node ${process.version}\n`);

  try {
    testDecodeUint256();
    testDecodeAddress();
    testDecodeBool();
    testDecodeHex();
    testParseTupleTypes();
    testDecodeParameterStatic();
    testDecodeParameterString();
    testDecodeParameterBytes();
    testDecodeParameterArrays();
    testDecodeParameterTuples();
    testDecodeParameterArrayOfTuples();
    testDecodeParameterMultipleReturns();
  } catch (err) {
    console.error("\nUNEXPECTED ERROR:", err);
  }

  console.log(`\n=== Results: ${testsPassed}/${testsRun} passed ===`);
  process.exit(testsPassed === testsRun ? 0 : 1);
}

main();
