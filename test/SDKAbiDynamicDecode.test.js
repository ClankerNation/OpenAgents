const { expect } = require("chai");
require("ts-node").register({
  compilerOptions: {
    ignoreDeprecations: "6.0",
    module: "commonjs",
    moduleResolution: "node",
    target: "es2020",
  },
  skipProject: true,
  transpileOnly: true,
});

const { decodeParameter, decodeParams } = require("../sdk/src/utils/encoding");

function word(value) {
  return BigInt(value).toString(16).padStart(64, "0");
}

function utf8Hex(value) {
  return Buffer.from(value, "utf8").toString("hex");
}

function dynamicBytes(valueHex) {
  const clean = valueHex.startsWith("0x") ? valueHex.slice(2) : valueHex;
  const paddedLength = Math.ceil(clean.length / 64) * 64;
  return word(clean.length / 2) + clean.padEnd(paddedLength, "0");
}

describe("ABI dynamic decoding", function () {
  it("decodes a complex return type with string, array, and uint", function () {
    const encoded =
      "0x" +
      word(0x60) +
      word(0xa0) +
      word(7) +
      dynamicBytes(utf8Hex("agent")) +
      word(3) +
      word(1) +
      word(2) +
      word(3);

    const decoded = decodeParams(["string", "uint256[]", "uint256"], encoded);

    expect(decoded).to.deep.equal(["agent", [1n, 2n, 3n], 7n]);
  });

  it("decodes bytes to a Buffer", function () {
    const encoded = "0x" + word(0x20) + dynamicBytes("1234abcd");

    const decoded = decodeParameter("bytes", encoded);

    expect(Buffer.isBuffer(decoded)).to.equal(true);
    expect(decoded.toString("hex")).to.equal("1234abcd");
  });

  it("decodes nested tuples recursively", function () {
    const tuple = {
      type: "tuple",
      components: [
        { type: "uint256" },
        {
          type: "tuple",
          components: [{ type: "string" }, { type: "uint256[]" }],
        },
      ],
    };
    const encoded =
      "0x" +
      word(0x20) +
      word(42) +
      word(0x40) +
      word(0x40) +
      word(0x80) +
      dynamicBytes(utf8Hex("nested")) +
      word(2) +
      word(8) +
      word(13);

    const decoded = decodeParameter(tuple, encoded);

    expect(decoded).to.deep.equal([42n, ["nested", [8n, 13n]]]);
  });

  it("decodes dynamic arrays of dynamic values", function () {
    const encoded =
      "0x" +
      word(0x20) +
      word(2) +
      word(0x60) +
      word(0xa0) +
      dynamicBytes(utf8Hex("alpha")) +
      dynamicBytes(utf8Hex("beta"));

    const decoded = decodeParameter("string[]", encoded);

    expect(decoded).to.deep.equal(["alpha", "beta"]);
  });
});
