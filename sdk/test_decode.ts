/**
 * Test suite for ABI decodeParameter — dynamic types (string, bytes, array, tuple).
 *
 * Usage: npx ts-node sdk/test_decode.ts
 */

import {
  decodeParameter,
  decodeString,
  decodeBytes,
  decodeArray,
  decodeTuple,
} from "./src/utils/encoding";

let passed = 0;
let failed = 0;

function assert(label: string, ok: boolean): void {
  if (ok) {
    passed++;
    console.log(`  ✅ ${label}`);
  } else {
    failed++;
    console.error(`  ❌ ${label}`);
  }
}

function assertEq(label: string, actual: any, expected: any): void {
  const ok =
    typeof expected === "bigint"
      ? actual === expected
      : Array.isArray(expected)
        ? Array.isArray(actual) &&
          actual.length === expected.length &&
          expected.every((e: any, i: number) =>
            typeof e === "bigint" ? actual[i] === e : actual[i] === e
          )
        : actual === expected;
  if (ok) {
    passed++;
    console.log(`  ✅ ${label}`);
  } else {
    failed++;
    console.error(`  ❌ ${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// ──────────────────────────────────────────
// Helper: build ABI-encoded hex for (string, uint256[], uint256)
// ──────────────────────────────────────────
function buildComplexReturn(str: string, arr: bigint[], num: bigint): string {
  const strLen = str.length;
  const strHex = Buffer.from(str, "utf-8").toString("hex");
  const arrLen = arr.length;

  // Head slots (each 32 bytes = 64 hex chars)
  const headSize = 3 * 32; // 96 bytes

  // String tail: starts after head
  const strOffset = headSize; // 96 bytes
  const strTail =
    BigInt(strLen).toString(16).padStart(64, "0") +
    strHex.padEnd(64, "0");

  // Array tail: starts after string tail
  const arrOffset = headSize + 32 + Math.ceil(strLen / 32) * 32;
  let arrTail =
    BigInt(arrLen).toString(16).padStart(64, "0");
  for (const v of arr) {
    arrTail += v.toString(16).padStart(64, "0");
  }

  // Head: offsets for dynamic types, value for static
  const head =
    BigInt(strOffset).toString(16).padStart(64, "0") +   // offset to string
    BigInt(arrOffset).toString(16).padStart(64, "0") +   // offset to array
    num.toString(16).padStart(64, "0");                  // uint256 value

  return "0x" + head + strTail + arrTail;
}

// ──────────────────────────────────────────
// Test 1: Decode string
// ──────────────────────────────────────────
console.log("\n📦 Testing decodeString:");
{
  // ABI: offset(0x20=32) → length(5) → "hello"
  const hex =
    "0x" +
    "0000000000000000000000000000000000000000000000000000000000000020" + // offset = 32 bytes
    "0000000000000000000000000000000000000000000000000000000000000005" + // length = 5
    "68656c6c6f000000000000000000000000000000000000000000000000000000";  // "hello"
  assertEq("decode string 'hello'", decodeString(hex), "hello");
}

// ──────────────────────────────────────────
// Test 2: Decode bytes
// ──────────────────────────────────────────
console.log("\n📦 Testing decodeBytes:");
{
  const hex =
    "0x" +
    "0000000000000000000000000000000000000000000000000000000000000020" + // offset = 32
    "0000000000000000000000000000000000000000000000000000000000000003" + // length = 3
    "aabbcc0000000000000000000000000000000000000000000000000000000000";  // 0xaabbcc
  assertEq("decode bytes", decodeBytes(hex), "0xaabbcc");
}

// ──────────────────────────────────────────
// Test 3: Decode uint256[] array
// ──────────────────────────────────────────
console.log("\n📦 Testing decodeArray:");
{
  const hex =
    "0x" +
    "0000000000000000000000000000000000000000000000000000000000000020" + // offset = 32
    "0000000000000000000000000000000000000000000000000000000000000003" + // length = 3
    "0000000000000000000000000000000000000000000000000000000000000001" + // 1
    "0000000000000000000000000000000000000000000000000000000000000002" + // 2
    "0000000000000000000000000000000000000000000000000000000000000003";  // 3
  const result = decodeArray("uint256", hex);
  assertEq("array length", result.length, 3);
  assertEq("array[0]", result[0], 1n);
  assertEq("array[1]", result[1], 2n);
  assertEq("array[2]", result[2], 3n);
}

// ──────────────────────────────────────────
// Test 4: decodeParameter with various types
// ──────────────────────────────────────────
console.log("\n📦 Testing decodeParameter:");
{
  assertEq("uint256 42",
    decodeParameter("uint256", "0x" + BigInt(42).toString(16).padStart(64, "0")),
    42n);
  assertEq("address",
    decodeParameter("address", "0x0000000000000000000000001234567890abcdef1234567890abcdef12345678"),
    "0x1234567890abcdef1234567890abcdef12345678");
  assertEq("bool true",
    decodeParameter("bool", "0x" + "1".padStart(64, "0")),
    true);
  assertEq("bool false",
    decodeParameter("bool", "0x" + "0".padStart(64, "0")),
    false);
}

// ──────────────────────────────────────────
// Test 5: Complex return type (string, uint256[], uint256)
// ──────────────────────────────────────────
console.log("\n📦 Testing complex return type (string + uint256[] + uint256):");
{
  const complexData = buildComplexReturn("hello", [1n, 2n, 3n], 42n);
  const result = decodeTuple(complexData, ["string", "uint256[]", "uint256"]) as any[];

  assertEq("tuple length", result.length, 3);
  assertEq("tuple[0] string", result[0], "hello");
  assertEq("tuple[1][0]", result[1][0], 1n);
  assertEq("tuple[1][1]", result[1][1], 2n);
  assertEq("tuple[1][2]", result[1][2], 3n);
  assertEq("tuple[2] uint256", result[2], 42n);
}

// ──────────────────────────────────────────
// Test 6: Complex return type (uint256, string, address)
// ──────────────────────────────────────────
console.log("\n📦 Testing complex return type (uint256 + string + address):");
{
  // Encode: (uint256: 999, string: "hi", address: 0xdead000000000000000000000000000000000001)
  const head = 3 * 32; // 96 bytes

  // Head slots
  const slot0 = BigInt(999).toString(16).padStart(64, "0");
  const strOffset = head; // slot1 = offset to string data = 96
  const slot1 = BigInt(strOffset).toString(16).padStart(64, "0");
  const slot2 = "000000000000000000000000dead000000000000000000000000000000000001"; // address in last slot

  // String tail at offset 96: length=2, data="hi"
  const strTail =
    BigInt(2).toString(16).padStart(64, "0") +
    "6869" + "0".repeat(60);

  const hex = "0x" + slot0 + slot1 + slot2 + strTail;
  const result = decodeTuple(hex, ["uint256", "string", "address"]) as any[];

  assertEq("tuple length", result.length, 3);
  assertEq("tuple[0]", result[0], 999n);
  assertEq("tuple[1]", result[1], "hi");
  assertEq("tuple[2]", result[2], "0xdead000000000000000000000000000000000001");
}

// ──────────────────────────────────────────
// Summary
// ──────────────────────────────────────────
console.log(`\n${"=".repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
} else {
  console.log("All tests passed! ✅");
}
