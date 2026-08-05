import assert from "node:assert/strict";
import test from "node:test";
import {
  applyGasMargin,
  parseRpcQuantity,
  toRpcQuantity,
  toRpcTransaction,
} from "../src/utils/gas.ts";

test("applies a rounded-up 20% margin", () => {
  assert.equal(applyGasMargin(100_000n, 200_000n), 120_000n);
  assert.equal(applyGasMargin(101n, 200n), 122n);
});

test("caps the padded estimate at the latest block gas limit", () => {
  assert.equal(applyGasMargin(90n, 100n), 100n);
});

test("supports explicit margin validation and RPC quantities", () => {
  assert.equal(toRpcQuantity(0n), "0x0");
  assert.equal(parseRpcQuantity("0x5208", "gas"), 21_000n);
  assert.throws(() => parseRpcQuantity("21000", "gas"), /hexadecimal/);
  assert.throws(() => applyGasMargin(1n, 100n, -1), /non-negative/);
});

test("serializes estimation input without losing zero values", () => {
  assert.deepEqual(
    toRpcTransaction({
      from: "0xabc",
      to: "0xdef",
      value: 0n,
      data: "0x1234",
    }),
    { from: "0xabc", to: "0xdef", value: "0x0", data: "0x1234" }
  );
});
