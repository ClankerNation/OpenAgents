/**
 * Tests for ABI encoding/decoding utilities.
 */

const {
  decodeParameter,
  decodeUint256,
  decodeAddress,
  decodeBool,
  encodeUint256,
  encodeAddress,
  encodeBool,
} = require("../utils/encoding");

function assert(condition, message) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

function test(name, fn) {
  try {
    fn();
    console.log(`✓ ${name}`);
  } catch (e) {
    console.error(`✗ ${name}`);
    console.error(`  ${e.message}`);
    process.exitCode = 1;
  }
}

console.log("Running encoding tests...\n");

// decodeParameter tests

test("decodes uint256", () => {
  const hex = "0x00000000000000000000000000000000000000000000000000000000000000ff";
  const result = decodeParameter(hex, "uint256");
  assert(result === 255n, `Expected 255n, got ${result}`);
});

test("decodes address", () => {
  const hex = "0x0000000000000000000000004bbeeb066ed09b7aed07bf39eee0460dfa261520";
  const result = decodeParameter(hex, "address");
  assert(result === "0x4bbeeb066ed09b7aed07bf39eee0460dfa261520", `Got ${result}`);
});

test("decodes bool true", () => {
  const hex = "0x0000000000000000000000000000000000000000000000000000000000000001";
  const result = decodeParameter(hex, "bool");
  assert(result === true, `Expected true, got ${result}`);
});

test("decodes bool false", () => {
  const hex = "0x0000000000000000000000000000000000000000000000000000000000000000";
  const result = decodeParameter(hex, "bool");
  assert(result === false, `Expected false, got ${result}`);
});

test("decodes string", () => {
  const hex =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000005" +
    "68656c6c6f000000000000000000000000000000000000000000000000000000";
  const result = decodeParameter("0x" + hex, "string");
  assert(result === "hello", `Expected "hello", got "${result}"`);
});

test("decodes bytes", () => {
  const hex =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000004" +
    "deadbeef00000000000000000000000000000000000000000000000000000000";
  const result = decodeParameter("0x" + hex, "bytes");
  assert(result instanceof Uint8Array, "Expected Uint8Array");
  assert(JSON.stringify(Array.from(result)) === JSON.stringify([0xde, 0xad, 0xbe, 0xef]), "Bytes mismatch");
});

test("decodes uint256 array", () => {
  const hex =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000002" +
    "0000000000000000000000000000000000000000000000000000000000000001" +
    "0000000000000000000000000000000000000000000000000000000000000002";
  const result = decodeParameter("0x" + hex, "uint256[]");
  assert(Array.isArray(result), "Expected array");
  assert(result.length === 2, `Expected 2 elements, got ${result.length}`);
  assert(result[0] === 1n, `Expected 1n, got ${result[0]}`);
  assert(result[1] === 2n, `Expected 2n, got ${result[1]}`);
});

test("decodes address array", () => {
  const addr = "4bbeeb066ed09b7aed07bf39eee0460dfa261520";
  const hex =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000001" +
    "000000000000000000000000" + addr;
  const result = decodeParameter("0x" + hex, "address[]");
  assert(Array.isArray(result), "Expected array");
  assert(result[0] === "0x" + addr, `Got ${result[0]}`);
});

test("throws on unsupported type", () => {
  let threw = false;
  try {
    decodeParameter("0x00", "tuple");
  } catch (e) {
    threw = true;
  }
  assert(threw, "Expected error to be thrown");
});

// Encode/decode roundtrip tests

test("roundtrips uint256", () => {
  const encoded = encodeUint256(12345n);
  const decoded = decodeUint256(encoded);
  assert(decoded === 12345n, `Expected 12345n, got ${decoded}`);
});

test("roundtrips address", () => {
  const addr = "0x4bbeeb066ed09b7aed07bf39eee0460dfa261520";
  const encoded = encodeAddress(addr);
  const decoded = decodeAddress(encoded);
  assert(decoded === addr.toLowerCase(), `Got ${decoded}`);
});

test("roundtrips bool", () => {
  const encodedTrue = encodeBool(true);
  const encodedFalse = encodeBool(false);
  assert(decodeBool(encodedTrue) === true, "True roundtrip failed");
  assert(decodeBool(encodedFalse) === false, "False roundtrip failed");
});

console.log("\nDone!");
