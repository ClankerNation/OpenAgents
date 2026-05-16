/**
 * Tests for encoding.ts — ABI encode/decode with dynamic types.
 * 
 * Run: npx ts-node --esm sdk/test/encoding.test.ts
 *   or: node --loader ts-node/esm sdk/test/encoding.test.ts
 * 
 * Expected output: "ALL TESTS PASSED" or "FAILURES: ..."
 */

// Simple test harness
let passed = 0;
let failed = 0;
const failures: string[] = [];

function assert(condition: boolean, msg: string) {
  if (condition) {
    passed++;
  } else {
    failed++;
    failures.push(`FAIL: ${msg}`);
  }
}

function stringify(v: any): string {
  if (typeof v === "bigint") return v.toString() + "n";
  if (v instanceof Uint8Array || Buffer.isBuffer(v)) return Buffer.from(v).toString("hex");
  return JSON.stringify(v);
}

function assertEq<T>(actual: T, expected: T, msg: string) {
  const a = stringify(actual);
  const e = stringify(expected);
  if (a === e) {
    passed++;
  } else {
    failed++;
    failures.push(`FAIL: ${msg}\n  expected: ${e}\n  actual:   ${a}`);
  }
}

// Load the module using dynamic import
async function runTests() {
  const mod = await import("../src/utils/encoding");

  console.log("=== encodeUint256 ===");
  assertEq(mod.encodeUint256(0n), "0".padStart(64, "0"), "encodeUint256(0)");
  assertEq(mod.encodeUint256(1n), "0".padStart(63, "0") + "1", "encodeUint256(1)");
  assertEq(mod.encodeUint256(255n), "0".padStart(62, "0") + "ff", "encodeUint256(255)");
  
  // Overflow check
  try {
    const max = (1n << 256n);
    mod.encodeUint256(max);
    assert(false, "encodeUint256 should reject overflow");
  } catch (e: any) {
    assert(e.message.includes("exceeds"), "encodeUint256 overflow rejected");
  }

  console.log("\n=== encodeAddress ===");
  assertEq(
    mod.encodeAddress("0x1234567890abcdef1234567890abcdef12345678"),
    "0000000000000000000000001234567890abcdef1234567890abcdef12345678",
    "encodeAddress with 0x prefix"
  );

  console.log("\n=== encodeBool ===");
  assertEq(mod.encodeBool(true), "0".padStart(63, "0") + "1", "encodeBool(true)");
  assertEq(mod.encodeBool(false), "0".padStart(64, "0"), "encodeBool(false)");

  console.log("\n=== decodeUint256 ===");
  // Test with 64 f's = max uint256
  assertEq(mod.decodeUint256("0x" + "f".repeat(64)), (1n << 256n) - 1n, "decodeUint256(max)");
  
  // Short value (no padding)
  assertEq(mod.decodeUint256("0x0a"), 10n, "decodeUint256 short value padded");
  assertEq(mod.decodeUint256("0x"), 0n, "decodeUint256 empty");

  console.log("\n=== decodeAddress ===");
  // Address in ABI: 12 zero bytes (24 hex chars) + 20 byte address (40 hex chars)
  const addressSlot = "000000000000000000000000dead00000000000000000000000000000000beef";
  assertEq(
    mod.decodeAddress(addressSlot),
    "0xdead00000000000000000000000000000000beef",
    "decodeAddress"
  );

  console.log("\n=== decodeBool ===");
  assertEq(mod.decodeBool("0x" + "0".padStart(63, "0") + "1"), true, "decodeBool(true)");
  assertEq(mod.decodeBool("0x" + "0".padStart(64, "0")), false, "decodeBool(false)");

  console.log("\n=== decodeHex ===");
  assertEq(mod.decodeHex("0xff"), 255n, "decodeHex 0xff");
  assertEq(mod.decodeHex("0x0"), 0n, "decodeHex 0x0");
  
  try {
    mod.decodeHex("0xghij");
    assert(false, "decodeHex should reject invalid hex");
  } catch (e: any) {
    assert(e.message.includes("invalid"), "decodeHex invalid hex rejected");
  }

  console.log("\n=== decodeString ===");
  // ABI encoded string "hello": offset(32) -> length(5) -> "68656c6c6f" + padding
  const helloEncoded = 
    "0000000000000000000000000000000000000000000000000000000000000020" + // offset 32
    "0000000000000000000000000000000000000000000000000000000000000005" + // length 5
    "68656c6c6f000000000000000000000000000000000000000000000000000000";  // "hello"
  
  assertEq(mod.decodeString("0x" + helloEncoded, 32), "hello", "decodeString 'hello'");

  console.log("\n=== decodeBytes ===");
  // ABI encoded bytes "0xdeadbeef": offset(32) -> length(4) -> "deadbeef" + padding
  const bytesEncoded =
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000004" +
    "deadbeef00000000000000000000000000000000000000000000000000000000";
  
  const decoded = mod.decodeBytes("0x" + bytesEncoded, 32);
  assert(Buffer.from(decoded).toString("hex") === "deadbeef", "decodeBytes 'deadbeef'");

  console.log("\n=== decodeArray (uint256[]) ===");
  // ABI encoded uint256[] [1,2,3]:
  const arrayEncoded =
    "0000000000000000000000000000000000000000000000000000000000000020" + // offset
    "0000000000000000000000000000000000000000000000000000000000000003" + // length
    "0000000000000000000000000000000000000000000000000000000000000001" + // [0]
    "0000000000000000000000000000000000000000000000000000000000000002" + // [1]
    "0000000000000000000000000000000000000000000000000000000000000003";  // [2]
  
  const arr = mod.decodeArray("0x" + arrayEncoded, "uint256", 32);
  assertEq(arr.map((n: bigint) => n.toString()), ["1","2","3"], "decodeArray [1,2,3]");

  console.log("\n=== decodeParameter: uint256 ===");
  const uintEncoded = "0x" + "000000000000000000000000000000000000000000000000000000000000002a"; // 42
  assertEq(mod.decodeParameter(uintEncoded, "uint256"), 42n, "decodeParameter uint256=42");

  console.log("\n=== decodeParameter: address ===");
  const addrEncoded = "0x" + "000000000000000000000000dead00000000000000000000000000000000beef";
  assertEq(
    mod.decodeParameter(addrEncoded, "address"),
    "0xdead00000000000000000000000000000000beef",
    "decodeParameter address"
  );

  console.log("\n=== decodeParameter: bool ===");
  assertEq(mod.decodeParameter("0x" + "0".padStart(63, "0") + "1", "bool"), true, "decodeParameter bool=true");

  console.log("\n=== decodeParameter: string ===");
  const strParam = 
    "0x" +
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "000000000000000000000000000000000000000000000000000000000000000b" +
    "48656c6c6f20576f726c64000000000000000000000000000000000000000000"; // "Hello World"
  assertEq(mod.decodeParameter(strParam, "string"), "Hello World", "decodeParameter string");

  console.log("\n=== decodeParameter: bytes ===");
  const bytesParam =
    "0x" +
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000002" +
    "cafe000000000000000000000000000000000000000000000000000000000000";
  const bytesResult = mod.decodeParameter(bytesParam, "bytes");
  assert(Buffer.from(bytesResult).toString("hex") === "cafe", "decodeParameter bytes=cafe");

  console.log("\n=== decodeParameter: uint256[] ===");
  const arrParam =
    "0x" +
    "0000000000000000000000000000000000000000000000000000000000000020" +
    "0000000000000000000000000000000000000000000000000000000000000003" +
    "000000000000000000000000000000000000000000000000000000000000000a" +
    "0000000000000000000000000000000000000000000000000000000000000014" +
    "000000000000000000000000000000000000000000000000000000000000001e";
  const arrResult = mod.decodeParameter(arrParam, "uint256[]");
  assertEq(arrResult.map((n: bigint) => n.toString()), ["10","20","30"], "decodeParameter uint256[]");

  console.log("\n=== decodeParameter: complex (string + uint256[]) ===");
  // A complex return type with a string and an array
  // We decode each separately from their offsets
  
  console.log("\n=== decodeTuple ===");
  // Tuple (uint256, address, bool): all static, just 3 consecutive slots
  const tupleEncoded =
    "0x" +
    "000000000000000000000000000000000000000000000000000000000000002a" + // uint256: 42
    "000000000000000000000000dead00000000000000000000000000000000beef" + // address
    "0000000000000000000000000000000000000000000000000000000000000001";  // bool: true
  const tupleResult = mod.decodeTuple(tupleEncoded, ["uint256", "address", "bool"], 0);
  assertEq(tupleResult[0], 42n, "tuple[0] uint256=42");
  assertEq(tupleResult[1], "0xdead00000000000000000000000000000000beef", "tuple[1] address");
  assertEq(tupleResult[2], true, "tuple[2] bool=true");

  console.log("\n=== decodeParameter: tuple(uint256,address) ===");
  const tupleParam =
    "0x" +
    "000000000000000000000000000000000000000000000000000000000000002a" +
    "000000000000000000000000dead00000000000000000000000000000000beef";
  const tResult = mod.decodeParameter(tupleParam, "tuple(uint256,address)");
  assertEq(tResult[0], 42n, "decodeParameter tuple[0]=42");
  assertEq(tResult[1], "0xdead00000000000000000000000000000000beef", "decodeParameter tuple[1]=addr");

  // ─── Results ───
  console.log(`\n${"=".repeat(50)}`);
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);
  if (failures.length > 0) {
    console.log("\nFAILURES:");
    for (const f of failures) console.log(`  ${f}`);
    process.exit(1);
  } else {
    console.log("ALL TESTS PASSED ✅");
  }
}

runTests().catch((err) => {
  console.error("Test runner error:", err);
  process.exit(1);
});
