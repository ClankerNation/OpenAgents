import { decodeParameter } from "./sdk/src/utils/encoding";

let passed = 0, failed = 0;
function assert(cond: boolean, msg: string) {
  if (cond) { console.log("  ok -", msg); passed++; }
  else { console.error("  FAIL -", msg); failed++; }
}

// Build a hand-coded ABI return: (uint256 a, string b, address[] c)
// head: a=42, string@96, array@128
const head =
  "000000000000000000000000000000000000000000000000000000000000002a" + // 42
  "0000000000000000000000000000000000000000000000000000000000000060" + // string offset = 96
  "00000000000000000000000000000000000000000000000000000000000000a0"; // array offset = 160
const stringData =
  "0000000000000000000000000000000000000000000000000000000000000005" + // length 5
  "68656c6c6f000000000000000000000000000000000000000000000000000000"; // "hello"
const arrayData =
  "0000000000000000000000000000000000000000000000000000000000000002" + // length 2
  "0000000000000000000000001111111111111111111111111111111111111111" +
  "0000000000000000000000002222222222222222222222222222222222222222";

const data = "0x" + head + stringData + arrayData;
const [a, b, c] = decodeParameter(data, ["uint256", "string", "address[]"]);

console.log("test: complex return (uint256 + string + address[])");
assert(a === 42n, "uint256 = 42, got " + a);
assert(b === "hello", "string = 'hello', got '" + b + "'");
assert(Array.isArray(c) && c.length === 2, "array length 2");
assert(c[0] === "0x1111111111111111111111111111111111111111", "addr[0] correct");
assert(c[1] === "0x2222222222222222222222222222222222222222", "addr[1] correct");

// fixed types only
console.log("test: fixed types (uint256 + address + bool)");
const fixedData = "0x" +
  "0000000000000000000000000000000000000000000000000000000000000001" +
  "000000000000000000000000abcdabcdabcdabcdabcdabcdabcdabcdabcdabcd" +
  "0000000000000000000000000000000000000000000000000000000000000001";
const [u, addr, flag] = decodeParameter(fixedData, ["uint256", "address", "bool"]);
assert(u === 1n, "uint = 1");
assert(addr === "0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd", "address correct, got " + addr);
assert(flag === true, "bool = true");

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
