/**
 * @fix-author kejuunuy
 * Tests for SDK encoding/decoding utilities — issue #198.
 *
 * Validates that decodeParameter handles both static and dynamic ABI types:
 *   - Static: uint256, address, bool, bytes32, fixed-size static arrays
 *   - Dynamic: string, bytes, dynamic arrays (T[]), fixed-size arrays of
 *     dynamic types (T[N] where T is dynamic)
 */

import {
  decodeParameter,
  decodeParameters,
  encodeUint256,
} from "../src/utils/encoding";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

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
  const repr = (v: any) =>
    typeof v === "bigint" ? `${v}n` : JSON.stringify(v);
  const eq =
    typeof expected === "bigint"
      ? actual === expected
      : repr(actual) === repr(expected);
  assert(eq, `${message}  (got: ${repr(actual)}, expected: ${repr(expected)})`);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Pad a hex string (no 0x) to exactly 64 chars, left-padded with zeros. */
function pad32(hex: string): string {
  return hex.replace(/^0x/, "").padStart(64, "0");
}

/** Pad hex data LEFT-aligned in a 32-byte word (right-padded with zeros). */
function pad32Left(hex: string): string {
  return hex.replace(/^0x/, "").padEnd(64, "0");
}

// ---------------------------------------------------------------------------
// Tests — Static types (backwards compat)
// ---------------------------------------------------------------------------

function testDecodeStaticUint256() {
  console.log("\n🔢 decodeParameter — static uint256");

  const data = "0x" + encodeUint256(42n);
  assertEqual(decodeParameter("uint256", data), 42n, "decodes uint256 value 42");

  const data2 = "0x" + encodeUint256(0n);
  assertEqual(decodeParameter("uint256", data2), 0n, "decodes uint256 value 0");

  const big = BigInt("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");
  const data3 = "0x" + encodeUint256(big);
  assertEqual(decodeParameter("uint256", data3), big, "decodes max uint256");
}

function testDecodeStaticAddress() {
  console.log("\n📍 decodeParameter — static address");

  // Address is 40 hex chars, right-aligned in a 32-byte (64 hex char) word
  const addr40 = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"; // 40 hex chars
  const data = "0x" + pad32(addr40);
  assertEqual(
    decodeParameter("address", data),
    "0x" + addr40,
    "decodes address"
  );
}

function testDecodeStaticBool() {
  console.log("\n✅ decodeParameter — static bool");

  const dataTrue = "0x" + encodeUint256(1n);
  assertEqual(decodeParameter("bool", dataTrue), true, "decodes bool true");

  const dataFalse = "0x" + encodeUint256(0n);
  assertEqual(decodeParameter("bool", dataFalse), false, "decodes bool false");
}

function testDecodeStaticBytes32() {
  console.log("\n📦 decodeParameter — static bytes32");

  // bytes32 returns the full 32 bytes of the word (the first 64 hex chars)
  const word = "deadbeef" + "0".repeat(56); // 64 hex chars total
  const data = "0x" + word;
  assertEqual(
    decodeParameter("bytes32", data),
    "0xdeadbeef" + "0".repeat(56),
    "decodes bytes32 full word"
  );
}

function testDecodeStaticUint256Array() {
  console.log("\n🔢 decodeParameter — static uint256[3]");

  const data =
    "0x" +
    encodeUint256(10n) +
    encodeUint256(20n) +
    encodeUint256(30n);
  const result = decodeParameter("uint256[3]", data);
  assertEqual(result[0], 10n, "uint256[3] element 0");
  assertEqual(result[1], 20n, "uint256[3] element 1");
  assertEqual(result[2], 30n, "uint256[3] element 2");
}

// ---------------------------------------------------------------------------
// Tests — Dynamic types (issue #198)
// ---------------------------------------------------------------------------

function testDecodeString() {
  console.log("\n📝 decodeParameter — dynamic string");

  // ABI encoding of string "hello":
  //   head[0] = offset (32 = 0x20)
  //   tail[0] = length (5)
  //   tail[1] = "hello" + padding
  const str = "hello";
  const hexStr = Buffer.from(str).toString("hex");
  const full =
    "0x" +
    pad32("20") + // offset = 32
    pad32("05") + // length = 5
    pad32Left(hexStr); // "hello" right-padded to 32 bytes

  assertEqual(decodeParameter("string", full), str, 'decodes string "hello"');
}

function testDecodeStringWorld() {
  console.log("\n📝 decodeParameter — dynamic string \"world\"");

  const str = "world";
  const hexStr = Buffer.from(str).toString("hex");
  const full =
    "0x" +
    pad32("20") + // offset = 32
    pad32("05") + // length = 5
    pad32Left(hexStr); // "world" right-padded

  assertEqual(decodeParameter("string", full), str, 'decodes string "world"');
}

function testDecodeBytes() {
  console.log("\n📦 decodeParameter — dynamic bytes");

  // bytes 0xdeadbeef: offset(32) | length(4) | data(deadbeef + padding)
  const full =
    "0x" +
    pad32("20") + // offset = 32
    pad32("04") + // length = 4
    pad32Left("deadbeef"); // data left-aligned

  assertEqual(decodeParameter("bytes", full), "0xdeadbeef", "decodes bytes 0xdeadbeef");
}

function testDecodeUint256DynamicArray() {
  console.log("\n🔢 decodeParameter — dynamic uint256[]");

  // uint256[] = [1, 2, 3]
  const full =
    "0x" +
    pad32("20") + // offset = 32
    pad32("03") + // length = 3
    pad32("01") + // element 0 = 1
    pad32("02") + // element 1 = 2
    pad32("03");  // element 2 = 3

  const result = decodeParameter("uint256[]", full);
  assert(Array.isArray(result), "uint256[] returns array");
  assertEqual(result.length, 3, "uint256[] has 3 elements");
  assertEqual(result[0], 1n, "uint256[] element 0 = 1");
  assertEqual(result[1], 2n, "uint256[] element 1 = 2");
  assertEqual(result[2], 3n, "uint256[] element 2 = 3");
}

function testDecodeAddressDynamicArray() {
  console.log("\n📍 decodeParameter — dynamic address[]");

  const addr1 = "1111111111111111111111111111111111111111";
  const addr2 = "2222222222222222222222222222222222222222";

  const full =
    "0x" +
    pad32("20") + // offset = 32
    pad32("02") + // length = 2
    pad32(addr1) + // element 0
    pad32(addr2);  // element 1

  const result = decodeParameter("address[]", full);
  assert(Array.isArray(result), "address[] returns array");
  assertEqual(result.length, 2, "address[] has 2 elements");
  assertEqual(result[0], "0x" + addr1, "address[] element 0");
  assertEqual(result[1], "0x" + addr2, "address[] element 1");
}

function testDecodeStringArray() {
  console.log("\n📝 decodeParameter — dynamic string[] (nested dynamic)");

  // string[] = ["hello", "hi"]
  //
  // Layout:
  //   [0x00] head:  offset to array data = 0x20 (32)
  //   [0x20] array length = 2
  //   [0x40] elem 0 offset (relative to array data start at 0x20) = 0x40
  //   [0x60] elem 1 offset = 0x80
  //   [0x80] string 0 length = 5
  //   [0xa0] string 0 data = "hello"
  //   [0xc0] string 1 length = 2
  //   [0xe0] string 1 data = "hi"

  const helloHex = Buffer.from("hello").toString("hex");
  const hiHex = Buffer.from("hi").toString("hex");

  const full =
    "0x" +
    pad32("20") + // head: offset to array data
    pad32("02") + // array length = 2
    pad32("40") + // elem 0 offset = 64 (relative to 0x20)
    pad32("80") + // elem 1 offset = 128 (relative to 0x20)
    pad32("05") + // string 0 length = 5
    pad32Left(helloHex) + // string 0 data "hello"
    pad32("02") + // string 1 length = 2
    pad32Left(hiHex); // string 1 data "hi"

  const result = decodeParameter("string[]", full);
  assert(Array.isArray(result), "string[] returns array");
  assertEqual(result.length, 2, "string[] has 2 elements");
  assertEqual(result[0], "hello", 'string[] element 0 = "hello"');
  assertEqual(result[1], "hi", 'string[] element 1 = "hi"');
}

function testDecodeDynamicByteArray() {
  console.log("\n📦 decodeParameter — dynamic bytes[]");

  // bytes[] = [0xaa, 0xbbcc]
  // Data within each bytes payload is LEFT-aligned (right-padded)
  const full =
    "0x" +
    pad32("20") + // head: offset to array data
    pad32("02") + // array length = 2
    pad32("40") + // elem 0 offset = 64 (relative to array data start)
    pad32("80") + // elem 1 offset = 128
    pad32("01") + // bytes 0 length = 1
    pad32Left("aa") + // bytes 0 data = 0xaa (left-aligned)
    pad32("02") + // bytes 1 length = 2
    pad32Left("bbcc"); // bytes 1 data = 0xbbcc (left-aligned)

  const result = decodeParameter("bytes[]", full);
  assert(Array.isArray(result), "bytes[] returns array");
  assertEqual(result.length, 2, "bytes[] has 2 elements");
  assertEqual(result[0], "0xaa", "bytes[] element 0 = 0xaa");
  assertEqual(result[1], "0xbbcc", "bytes[] element 1 = 0xbbcc");
}

// ---------------------------------------------------------------------------
// Tests — decodeParameters (multi-param)
// ---------------------------------------------------------------------------

function testDecodeMultipleParams() {
  console.log("\n📋 decodeParameters — multiple mixed params");

  // (uint256=42, string="hi")
  const hiHex = Buffer.from("hi").toString("hex");
  const full =
    "0x" +
    pad32("2a") + // uint256 = 42
    pad32("40") + // offset to string = 64 (two head words)
    pad32("02") + // string length = 2
    pad32Left(hiHex); // "hi" right-padded

  const result = decodeParameters(["uint256", "string"], full);
  assertEqual(result.length, 2, "returns 2 values");
  assertEqual(result[0], 42n, "first param is uint256 = 42");
  assertEqual(result[1], "hi", 'second param is string "hi"');
}

function testDecodeMultipleStaticParams() {
  console.log("\n📋 decodeParameters — multiple static params");

  // (uint256=100, address=0xabc..., bool=true)
  const addr40 = "abcdefabcdefabcdefabcdefabcdefabcdefabcd";
  const full =
    "0x" +
    pad32("64") + // uint256 = 100
    pad32(addr40) + // address
    pad32("01"); // bool = true

  const result = decodeParameters(["uint256", "address", "bool"], full);
  assertEqual(result[0], 100n, "uint256 = 100");
  assertEqual(result[1], "0x" + addr40, "address decoded");
  assertEqual(result[2], true, "bool = true");
}

// ---------------------------------------------------------------------------
// Tests — Edge cases
// ---------------------------------------------------------------------------

function testDecodeEmptyString() {
  console.log("\n📝 decodeParameter — empty string");

  const full =
    "0x" +
    pad32("20") + // offset = 32
    pad32("00");   // length = 0

  assertEqual(decodeParameter("string", full), "", "decodes empty string");
}

function testDecodeEmptyBytes() {
  console.log("\n📦 decodeParameter — empty bytes");

  const full =
    "0x" +
    pad32("20") + // offset = 32
    pad32("00");   // length = 0

  assertEqual(decodeParameter("bytes", full), "0x", "decodes empty bytes");
}

function testDecodeEmptyDynamicArray() {
  console.log("\n🔢 decodeParameter — empty uint256[]");

  const full =
    "0x" +
    pad32("20") + // offset = 32
    pad32("00");   // length = 0

  const result = decodeParameter("uint256[]", full);
  assert(Array.isArray(result), "empty array is array");
  assertEqual(result.length, 0, "empty array has 0 elements");
}

function testDecodeWith0xPrefix() {
  console.log("\n🔧 decodeParameter — accepts 0x prefix");

  const data = "0x" + encodeUint256(99n);
  assertEqual(decodeParameter("uint256", data), 99n, "works with 0x prefix");
}

function testDecodeWithout0xPrefix() {
  console.log("\n🔧 decodeParameter — works without 0x prefix");

  const data = encodeUint256(77n);
  assertEqual(decodeParameter("uint256", data), 77n, "works without 0x prefix");
}

function testDecodeWithByteOffset() {
  console.log("\n🔧 decodeParameter — custom byteOffset");

  const data = "0x" + encodeUint256(10n) + encodeUint256(20n);
  assertEqual(
    decodeParameter("uint256", data, 32),
    20n,
    "reads at byteOffset=32"
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  console.log("🧪 SDK encoding.ts — decodeParameter Test Suite (issue #198)\n");

  try {
    // Static types (backwards compat)
    testDecodeStaticUint256();
    testDecodeStaticAddress();
    testDecodeStaticBool();
    testDecodeStaticBytes32();
    testDecodeStaticUint256Array();

    // Dynamic types (new)
    testDecodeString();
    testDecodeStringWorld();
    testDecodeBytes();
    testDecodeUint256DynamicArray();
    testDecodeAddressDynamicArray();
    testDecodeStringArray();
    testDecodeDynamicByteArray();

    // Multi-param
    testDecodeMultipleParams();
    testDecodeMultipleStaticParams();

    // Edge cases
    testDecodeEmptyString();
    testDecodeEmptyBytes();
    testDecodeEmptyDynamicArray();
    testDecodeWith0xPrefix();
    testDecodeWithout0xPrefix();
    testDecodeWithByteOffset();
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
