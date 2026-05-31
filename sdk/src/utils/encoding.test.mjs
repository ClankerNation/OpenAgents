import assert from "node:assert/strict";
import { test } from "node:test";
import { AbiCoder } from "ethers";

import {
  decodeParameter,
  decodeParameters,
  decodeParams,
  decodeUint256,
} from "./encoding.ts";

const coder = AbiCoder.defaultAbiCoder();

test("decodeParameter preserves fixed-width backwards compatibility", () => {
  const address = "0x000000000000000000000000000000000000dEaD";
  const bytes32 = `0x${"ab".repeat(32)}`;

  assert.equal(decodeParameter("uint256", coder.encode(["uint256"], [42n])), 42n);
  assert.equal(decodeParameter("uint256", "0x2a"), 42n);
  assert.equal(decodeUint256("0x2a"), 42n);
  assert.equal(
    decodeParameter("address", coder.encode(["address"], [address])),
    address.toLowerCase(),
  );
  assert.equal(decodeParameter("bool", coder.encode(["bool"], [true])), true);
  assert.equal(decodeParameter("bytes32", coder.encode(["bytes32"], [bytes32])), bytes32);
});

test("decodeParameter decodes dynamic string and bytes payloads", () => {
  const bytesValue = "0x1234567890";

  assert.equal(
    decodeParameter("string", coder.encode(["string"], ["live demo flow"])),
    "live demo flow",
  );

  const decodedBytes = decodeParameter("bytes", coder.encode(["bytes"], [bytesValue]));
  assert.ok(Buffer.isBuffer(decodedBytes));
  assert.equal(decodedBytes.toString("hex"), bytesValue.slice(2));
});

test("decodeParams decodes complex return data with string, array, and uint", () => {
  const types = ["string", "uint256[]", "uint256"];
  const encoded = coder.encode(types, ["agent-alpha", [3n, 5n, 8n], 13n]);
  const expected = ["agent-alpha", [3n, 5n, 8n], 13n];

  assert.deepEqual(decodeParams(types, encoded), expected);
  assert.deepEqual(decodeParameters(types, encoded), expected);
  assert.equal(decodeParameter("string", encoded, 0), "agent-alpha");
  assert.deepEqual(decodeParameter("uint256[]", encoded, 32), [3n, 5n, 8n]);
  assert.equal(decodeParameter("uint256", encoded, 64), 13n);
});

test("decodeParameter decodes nested tuple values recursively", () => {
  const tupleType = "(string,uint256[],uint256,(bool,string))";
  const value = ["validator", [7n, 11n], 19n, [true, "ready"]];
  const encoded = coder.encode([tupleType], [value]);

  assert.deepEqual(decodeParameter(tupleType, encoded), value);
});

test("decodeParameter supports tuple descriptors and dynamic tuple arrays", () => {
  const descriptor = {
    type: "tuple[]",
    components: [
      { type: "string", name: "name" },
      { type: "uint256", name: "score" },
      { type: "bytes", name: "payload" },
    ],
  };
  const abiType = "(string,uint256,bytes)[]";
  const encoded = coder.encode(
    [abiType],
    [
      [
        ["one", 1n, "0x0102"],
        ["two", 2n, "0x030405"],
      ],
    ],
  );

  const decoded = decodeParameter(descriptor, encoded);
  assert.deepEqual(decoded[0].slice(0, 2), ["one", 1n]);
  assert.deepEqual(decoded[1].slice(0, 2), ["two", 2n]);
  assert.ok(Buffer.isBuffer(decoded[0][2]));
  assert.ok(Buffer.isBuffer(decoded[1][2]));
  assert.equal(decoded[0][2].toString("hex"), "0102");
  assert.equal(decoded[1][2].toString("hex"), "030405");
});

test("decodeParameter decodes dynamic arrays of dynamic elements", () => {
  assert.deepEqual(
    decodeParameter("string[]", coder.encode(["string[]"], [["red", "blue"]])),
    ["red", "blue"],
  );

  const decodedBytesArray = decodeParameter(
    "bytes[]",
    coder.encode(["bytes[]"], [["0xaaaa", "0xbbccdd"]]),
  );
  assert.deepEqual(
    decodedBytesArray.map((entry) => entry.toString("hex")),
    ["aaaa", "bbccdd"],
  );
});

test("decodeParameter rejects malformed dynamic data and unsafe dimensions", () => {
  assert.throws(
    () => decodeParameter("uint256", "0xnot-hex"),
    /Invalid ABI hex data/,
  );
  assert.throws(
    () => decodeParameter("string", "0x20"),
    /out of bounds/,
  );
  assert.throws(
    () => decodeParameter("uint256[100001]", coder.encode(["uint256"], [1n])),
    /array length exceeds supported limit/,
  );

  const encoded = coder.encode(["string"], ["truncated"]);
  assert.throws(
    () => decodeParameter("string", `0x${encoded.slice(2, 96)}`),
    /out of bounds/,
  );
});
