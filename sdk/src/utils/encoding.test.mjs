import test from "node:test";
import assert from "node:assert/strict";
import { AbiCoder } from "ethers";
import { decodeParameter } from "./encoding.ts";

const abiCoder = AbiCoder.defaultAbiCoder();

test("decodeParameter keeps static-slot backward compatibility", () => {
  const uintSlot = "2a".padStart(64, "0");
  const addressSlot = "0000000000000000000000001234567890abcdef1234567890abcdef12345678";

  assert.equal(decodeParameter("uint256", uintSlot), 42n);
  assert.equal(
    decodeParameter("address", addressSlot),
    "0x1234567890abcdef1234567890abcdef12345678"
  );
});

test("decodeParameter decodes dynamic string", () => {
  const encoded = abiCoder.encode(["string"], ["openagents"]);
  assert.equal(decodeParameter("string", encoded), "openagents");
});

test("decodeParameter decodes dynamic bytes to Buffer", () => {
  const encoded = abiCoder.encode(["bytes"], ["0x1234abcd"]);
  const decoded = decodeParameter("bytes", encoded);

  assert.ok(Buffer.isBuffer(decoded));
  assert.equal(decoded.toString("hex"), "1234abcd");
});

test("decodeParameter decodes dynamic array", () => {
  const encoded = abiCoder.encode(["uint256[]"], [[1n, 2n, 255n]]);
  assert.deepEqual(decodeParameter("uint256[]", encoded), [1n, 2n, 255n]);
});

test("decodeParameter decodes nested tuple recursively", () => {
  const tupleType = "(string,uint256[],uint256,(bool,string))";
  const value = ["agent", [7n, 8n], 9n, [true, "ok"]];
  const encoded = abiCoder.encode([tupleType], [value]);

  assert.deepEqual(decodeParameter(tupleType, encoded), value);
});
