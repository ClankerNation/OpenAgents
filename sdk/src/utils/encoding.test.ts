/**
 * Tests for encoding.ts — decodeParameter dynamic type support
 * Issue #198 — $9,300 bounty
 * 
 * Run: npx tsx sdk/src/utils/encoding.test.ts
 */

import {
  decodeParameter,
  decodeUint256,
  decodeAddress,
  decodeBool,
  decodeString,
  decodeBytes,
  decodeHex,
} from "./encoding";

// ─── Test Helpers ──────────────────────────────────────────

let passed = 0;
let failed = 0;

function assert(condition: boolean, msg: string): void {
  if (condition) {
    passed++;
    console.log(`  ✅ ${msg}`);
  } else {
    failed++;
    console.log(`  ❌ ${msg}`);
  }
}

function assertEq<T>(actual: T, expected: T, msg: string): void {
  // Deep comparison for objects and arrays
  const actualStr = JSON.stringify(actual, bigintReplacer);
  const expectedStr = JSON.stringify(expected, bigintReplacer);
  const ok = actualStr === expectedStr;
  if (ok) {
    passed++;
    console.log(`  ✅ ${msg}`);
  } else {
    failed++;
    console.log(`  ❌ ${msg}`);
    console.log(`     Expected: ${expectedStr}`);
    console.log(`     Actual:   ${actualStr}`);
  }
}

function assertThrows(fn: () => unknown, msg: string): void {
  try {
    fn();
    failed++;
    console.log(`  ❌ ${msg} — expected throw, but no error`);
  } catch {
    passed++;
    console.log(`  ✅ ${msg} — throws as expected`);
  }
}

function bigintReplacer(_key: string, value: unknown): unknown {
  if (typeof value === "bigint") return value.toString();
  return value;
}

// ─── ABI Encoding Helpers ──────────────────────────────────

function abiEncodeUint256(val: number | bigint): string {
  return BigInt(val).toString(16).padStart(64, "0");
}

function abiEncodeAddress(addr: string): string {
  return addr.slice(2).toLowerCase().padStart(64, "0");
}

function abiEncodeString(str: string): string {
  // Offset to dynamic data = 32 (one slot for the offset itself)
  const offset = abiEncodeUint256(32);
  const hex = Buffer.from(str, "utf8").toString("hex");
  const len = abiEncodeUint256(str.length);
  // Pad to 32-byte multiple
  const paddedHex = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return offset + len + paddedHex;
}

function abiEncodeBytes(data: Uint8Array): string {
  const offset = abiEncodeUint256(32);
  const hex = Buffer.from(data).toString("hex");
  const len = abiEncodeUint256(data.length);
  const paddedHex = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return offset + len + paddedHex;
}

function abiEncodeDynamicArray(elements: string[]): string {
  // Standard ABI encoding for string[]:
  // [0]: offset to dynamic data (the array body)
  // Body: [length][offset0][offset1]...[string_data0][string_data1]...
  // All per-element offsets are relative to START of body.

  const numElements = elements.length;
  
  // Pre-compute string hex data
  const hexStrings: string[] = elements.map(s => Buffer.from(s, "utf8").toString("hex"));
  
  // Per-element string encoding: len_slot(32) + padded_data
  const stringEncodings: string[] = hexStrings.map(h => {
    const padded = h.padEnd(Math.ceil(h.length / 64) * 64, "0");
    return abiEncodeUint256(h.length / 2) + padded;
  });

  // Body layout:
  // length_slot (32) + per-element offset slots (numElements * 32) + string encodings
  const lengthSlotSize = 32;
  const offsetSlotsSize = numElements * 32;
  const bodyStart = 0;

  // Compute per-element offsets (relative to body start)
  const offsets: number[] = [];
  let dataCursor = lengthSlotSize + offsetSlotsSize;
  for (const se of stringEncodings) {
    offsets.push(dataCursor);
    dataCursor += se.length / 2;  // se.length is hex chars, /2 = bytes
  }

  // Build head: offset to body
  const bodyOffset = 32;  // one 32-byte slot for the offset itself
  let head = abiEncodeUint256(bodyOffset);

  // Build body
  let body = abiEncodeUint256(numElements);
  for (const off of offsets) {
    body += abiEncodeUint256(off);
  }
  for (const se of stringEncodings) {
    body += se;
  }

  return head + body;
}

function abiEncodeUint256Array(vals: (number | bigint)[]): string {
  const dataStart = 32;
  let head = abiEncodeUint256(dataStart);
  let tail = abiEncodeUint256(vals.length);
  for (const v of vals) {
    tail += abiEncodeUint256(v);
  }
  return head + tail;
}

// ─── Tests ─────────────────────────────────────────────────

console.log("\n=== decodeUint256 ===");
assertEq(decodeUint256("0x000000000000000000000000000000000000000000000000000000000000002a"), 42n, "decodes 42");
// Test short value (BUGFIX)
assertEq(decodeUint256("0x2a"), 42n, "handles short slot (1 byte)");
assertEq(decodeUint256("0xff"), 255n, "handles short slot (0xff)");

console.log("\n=== decodeAddress ===");
assertEq(decodeAddress("0x0000000000000000000000004200000000000000000000000000000000000006"), "0x4200000000000000000000000000000000000006", "decodes address from padded slot");

console.log("\n=== decodeBool ===");
assertEq(decodeBool("0x0000000000000000000000000000000000000000000000000000000000000001"), true, "decodes true");
assertEq(decodeBool("0x0000000000000000000000000000000000000000000000000000000000000000"), false, "decodes false");

console.log("\n=== decodeHex (BUGFIX) ===");
assertEq(decodeHex("0xff"), 255n, "decodes 0xff");
assertThrows(() => decodeHex("nothex"), "throws on non-hex input");

console.log("\n=== decodeParameter — static types ===");
assertEq(decodeParameter("0x000000000000000000000000000000000000000000000000000000000000002a", "uint256"), 42n, "uint256 = 42");
assertEq(decodeParameter("0x0000000000000000000000000000000000000000000000000000000000000001", "bool"), true, "bool = true");
assertEq(
  decodeParameter("0x0000000000000000000000004200000000000000000000000000000000000006", "address"),
  "0x4200000000000000000000000000000000000006",
  "address decoded"
);

console.log("\n=== decodeParameter — string ===");
const helloEncoded = abiEncodeString("Hello, World!");
const helloDecoded = decodeParameter("0x" + helloEncoded, "string");
assertEq(helloDecoded, "Hello, World!", "string: 'Hello, World!'");

const emptyEncoded = abiEncodeString("");
assertEq(decodeParameter("0x" + emptyEncoded, "string"), "", "empty string");

console.log("\n=== decodeParameter — bytes ===");
const bytesData = new Uint8Array([0xde, 0xad, 0xbe, 0xef]);
const bytesEncoded = abiEncodeBytes(bytesData);
const bytesDecoded = decodeParameter("0x" + bytesEncoded, "bytes") as Uint8Array;
assertEq(Array.from(bytesDecoded), [0xde, 0xad, 0xbe, 0xef], "bytes: deadbeef");

console.log("\n=== decodeParameter — dynamic array (uint256[]) ===");
// uint256[] with [10, 20, 30]
const uintArrEncoded = abiEncodeUint256Array([10, 20, 30]);
const uintArrDecoded = decodeParameter("0x" + uintArrEncoded, "uint256[]") as bigint[];
assertEq(uintArrDecoded.length, 3, "uint256[] length = 3");
assertEq(uintArrDecoded[0], 10n, "uint256[] [0] = 10");
assertEq(uintArrDecoded[1], 20n, "uint256[] [1] = 20");
assertEq(uintArrDecoded[2], 30n, "uint256[] [2] = 30");

console.log("\n=== decodeParameter — dynamic array (string[]) ===");
const strArrEncoded = abiEncodeDynamicArray(["foo", "bar", "bazqux"]);
const strArrDecoded = decodeParameter("0x" + strArrEncoded, "string[]") as string[];
assertEq(strArrDecoded.length, 3, "string[] length = 3");
assertEq(strArrDecoded[0], "foo", "string[0] = 'foo'");
assertEq(strArrDecoded[1], "bar", "string[1] = 'bar'");
assertEq(strArrDecoded[2], "bazqux", "string[2] = 'bazqux'");

console.log("\n=== decodeParameter — tuple ===");
// tuple(uint256,address) — static-only tuple
// {uint256: 100, address: 0xdead...beef}
const staticTuple = "0x" +
  abiEncodeUint256(100) +
  abiEncodeAddress("0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF");
const tupleDecoded = decodeParameter(staticTuple, "tuple(uint256,address)") as Record<string, unknown>;
assertEq(tupleDecoded._0, 100n, "tuple._0 = 100");
assertEq(tupleDecoded._1, "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef", "tuple._1 = address");

console.log("\n=== decodeParameter — tuple with dynamic member ===");
// tuple(string,uint256) — "test" + 42
// Offset to string, then uint256 value
const dynTupleHead =
  abiEncodeUint256(64) +  // offset to string data (skip 2 slots: this offset + uint256)
  abiEncodeUint256(42);    // uint256 = 42
const dynTupleTail =
  abiEncodeUint256(4) +                          // string length = 4
  Buffer.from("test", "utf8").toString("hex").padEnd(64, "0"); // "test" padded
const dynTuple = "0x" + dynTupleHead + dynTupleTail;
const dynTupleDecoded = decodeParameter(dynTuple, "tuple(string,uint256)") as Record<string, unknown>;
assertEq(dynTupleDecoded._0, "test", "tuple._0 = 'test'");
assertEq(dynTupleDecoded._1, 42n, "tuple._1 = 42");

// ─── Results ───────────────────────────────────────────────

console.log(`\n${"=".repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
console.log(`${"=".repeat(50)}`);

if (failed > 0) {
  process.exit(1);
}
