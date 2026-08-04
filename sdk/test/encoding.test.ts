import assert from "node:assert/strict";
import { test } from "node:test";

import {
  decodeParameter,
  decodeParams,
  encodeParams,
} from "../src/utils/encoding.ts";

function word(value: bigint | number): string {
  return BigInt(value).toString(16).padStart(64, "0");
}

function paddedUtf8(value: string): string {
  const bytes = Buffer.from(value, "utf8").toString("hex");
  return bytes.padEnd(Math.ceil(bytes.length / 64) * 64, "0");
}

test("decodes a single dynamic string from the standard offset encoding", () => {
  const expected = `0x${word(32)}${word(5)}${paddedUtf8("hello")}`;
  assert.equal(decodeParameter("string", expected), "hello");
});

test("decodes mixed dynamic and static return values", () => {
  const encoded = encodeParams([
    { type: "string", value: "hello" },
    { type: "uint256", value: 7n },
    { type: "bytes", value: "0x0102" },
  ]);

  const [text, number, bytes] = decodeParams(
    ["string", "uint256", "bytes"],
    encoded,
  ) as [string, bigint, Uint8Array];

  assert.equal(text, "hello");
  assert.equal(number, 7n);
  assert.deepEqual([...bytes], [1, 2]);
});

test("decodes dynamic arrays with static and dynamic elements", () => {
  const encoded = encodeParams([
    { type: "uint256[]", value: [1n, 2n, 3n] },
    { type: "string[]", value: ["one", "two"] },
  ]);

  const [numbers, strings] = decodeParams(
    ["uint256[]", "string[]"],
    encoded,
  ) as [bigint[], string[]];

  assert.deepEqual(numbers, [1n, 2n, 3n]);
  assert.deepEqual(strings, ["one", "two"]);
});

test("decodes nested tuples and tuple arrays recursively", () => {
  const encoded = encodeParams([
    {
      type: "tuple(string,uint256)",
      value: ["first", 11n],
    },
    {
      type: "tuple(uint256,string)[]",
      value: [[1n, "one"], [2n, "two"]],
    },
  ]);

  const decoded = decodeParams(
    ["tuple(string,uint256)", "tuple(uint256,string)[]"],
    encoded,
  ) as [[string, bigint], [bigint, string][]];

  assert.deepEqual(decoded, [
    ["first", 11n],
    [[1n, "one"], [2n, "two"]],
  ]);
});

test("decodes the bounty's complex string + array + uint return shape", () => {
  const encoded = encodeParams([
    {
      type: "tuple(string,uint256[],uint256)",
      value: ["result", [4n, 5n], 99n],
    },
  ]);

  assert.deepEqual(
    decodeParameter("tuple(string,uint256[],uint256)", encoded),
    ["result", [4n, 5n], 99n],
  );
});

test("supports ABI JSON tuple definitions", () => {
  const type = {
    type: "tuple",
    components: [
      { type: "uint256" },
      { type: "tuple", components: [{ type: "string" }, { type: "bool" }] },
    ],
  } as const;
  const encoded = encodeParams([{ type, value: [42n, ["ok", true]] }]);

  assert.deepEqual(decodeParameter(type, encoded), [42n, ["ok", true]]);
});

test("decodes signed integer values using the declared bit width", () => {
  assert.equal(decodeParameter("int8", "0x" + "f".repeat(64)), -1n);
  assert.equal(decodeParameter("int8", "0x" + word(127)), 127n);
});

test("rejects offsets that point outside the payload", () => {
  assert.throws(
    () => decodeParameter("string", `0x${word(0x200)}`),
    /outside the payload|out of bounds/,
  );
});
