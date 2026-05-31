const assert = require("assert");
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
  moduleResolution: "node",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const {
  decodeHex,
  decodeInt256,
  decodeUint256,
  encodeAddress,
  encodeBytes32,
  encodeInt256,
  encodeParams,
  encodeUint256,
} = require("../sdk/src/utils/encoding.ts");

const UINT256_MAX = (1n << 256n) - 1n;
const INT256_MAX = (1n << 255n) - 1n;
const INT256_MIN = -(1n << 255n);

describe("SDK ABI encoding bounds", function () {
  it("throws on uint256 overflow and negative values", function () {
    assert.equal(encodeUint256(UINT256_MAX), "f".repeat(64));
    assert.throws(() => encodeUint256(UINT256_MAX + 1n), /out of bounds/);
    assert.throws(() => encodeUint256(-1n), /out of bounds/);
  });

  it("requires 0x prefixes for fixed hex input", function () {
    assert.throws(() => decodeHex("255"), /0x prefix/);
    assert.throws(() => encodeBytes32("abcd"), /0x prefix/);
    assert.throws(() => encodeAddress("000000000000000000000000000000000000dead"), /0x prefix/);
  });

  it("pads ABI words to 32 bytes", function () {
    assert.equal(encodeUint256(1n), "0".repeat(63) + "1");
    assert.equal(encodeAddress("0x000000000000000000000000000000000000dEaD").length, 64);
    assert.equal(encodeBytes32("0xabcd"), "abcd" + "0".repeat(60));
    assert.equal(decodeUint256("0x1"), 1n);
  });

  it("encodes and decodes signed int256 values", function () {
    assert.equal(encodeInt256(0n), "0".repeat(64));
    assert.equal(encodeInt256(-1n), "f".repeat(64));
    assert.equal(decodeInt256("0x" + "f".repeat(64)), -1n);
    assert.equal(encodeInt256(INT256_MAX), "7" + "f".repeat(63));
    assert.throws(() => encodeInt256(INT256_MAX + 1n), /out of bounds/);
    assert.throws(() => encodeInt256(INT256_MIN - 1n), /out of bounds/);
  });

  it("supports int256 in encodeParams", function () {
    const encoded = encodeParams([{ type: "int256", value: -1n }]);
    assert.equal(encoded, "0x" + "f".repeat(64));
  });
});
