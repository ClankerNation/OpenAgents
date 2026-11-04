import { expect } from "chai";
import { AbiCoder } from "ethers";
import {
  decodeParameter,
  decodeParameters,
  parseType,
  encodeParams,
  decodeUint256,
} from "../sdk/src/utils/encoding.ts";

const coder = AbiCoder.defaultAbiCoder();
const encode = (types: string[], values: unknown[]) => coder.encode(types, values);

describe("decodeParameter dynamic types", function () {
  it("decodes a string, including multibyte characters", function () {
    const data = encode(["string"], ["hello wörld — こんにちは"]);
    expect(decodeParameter("string", data)).to.equal("hello wörld — こんにちは");
  });

  it("decodes an empty string", function () {
    expect(decodeParameter("string", encode(["string"], [""]))).to.equal("");
  });

  it("decodes bytes as a Uint8Array of the exact payload", function () {
    const payload = "0xdeadbeef00ff";
    const decoded = decodeParameter("bytes", encode(["bytes"], [payload])) as Uint8Array;
    expect(decoded).to.be.instanceOf(Uint8Array);
    expect(Buffer.from(decoded).toString("hex")).to.equal(payload.slice(2));
  });

  it("decodes a dynamic uint256 array", function () {
    const data = encode(["uint256[]"], [[1n, 2n, 3n]]);
    expect(decodeParameter("uint256[]", data)).to.deep.equal([1n, 2n, 3n]);
  });

  it("decodes an empty array", function () {
    expect(decodeParameter("uint256[]", encode(["uint256[]"], [[]]))).to.deep.equal([]);
  });

  it("decodes an array of strings", function () {
    const data = encode(["string[]"], [["a", "bb", "ccc"]]);
    expect(decodeParameter("string[]", data)).to.deep.equal(["a", "bb", "ccc"]);
  });

  it("decodes a fixed-size array laid out inline", function () {
    const data = encode(["uint256[3]"], [[7n, 8n, 9n]]);
    expect(decodeParameter("uint256[3]", data)).to.deep.equal([7n, 8n, 9n]);
    expect(parseType("uint256[3]")).to.deep.equal({
      kind: "array",
      item: { kind: "static", type: "uint256" },
      length: 3,
    });
  });

  it("decodes a tuple with mixed static and dynamic members", function () {
    const data = encode(["tuple(uint256,string)"], [[42n, "why"]]);
    const decoded = decodeParameter("(uint256,string)", data) as Record<number, unknown>;
    expect(decoded[0]).to.equal(42n);
    expect(decoded[1]).to.equal("why");
  });

  it("decodes nested tuples recursively", function () {
    const types = ["tuple(string,uint256[],tuple(bool,bytes))"];
    const values = [["outer", [5n, 6n], [true, "0x0102"]]];
    const decoded = decodeParameter("(string,uint256[],(bool,bytes))", encode(types, values)) as any;

    expect(decoded[0]).to.equal("outer");
    expect(decoded[1]).to.deep.equal([5n, 6n]);
    expect(decoded[2][0]).to.equal(true);
    expect(Buffer.from(decoded[2][1]).toString("hex")).to.equal("0102");
  });

  it("decodes the complex return type from the issue: string + array + uint", function () {
    const data = encode(["string", "uint256[]", "uint256"], ["note", [10n, 20n], 99n]);
    const [text, list, tail] = decodeParameters(["string", "uint256[]", "uint256"], data);
    expect(text).to.equal("note");
    expect(list).to.deep.equal([10n, 20n]);
    expect(tail).to.equal(99n);
  });

  it("decodes a negative int256", function () {
    expect(decodeParameter("int256", encode(["int256"], [-5n]))).to.equal(-5n);
    expect(decodeParameter("int256", encode(["int256"], [-(2n ** 255n)]))).to.equal(-(2n ** 255n));
  });

  it("leaves the static decoders alone", function () {
    const data = encode(["address", "bool", "bytes32"], [
      "0x1111111111111111111111111111111111111111",
      true,
      "0x" + "ab".repeat(32),
    ]);
    const [addr, flag, digest] = decodeParameters(["address", "bool", "bytes32"], data);
    expect(addr).to.equal("0x1111111111111111111111111111111111111111");
    expect(flag).to.equal(true);
    expect(digest).to.equal("0x" + "ab".repeat(32));
    expect(decodeUint256("0".repeat(64))).to.equal(0n);
  });

  it("throws when the payload is truncated rather than returning junk", function () {
    const data = encode(["string"], ["truncated"]);
    expect(() => decodeParameter("string", data.slice(0, 96))).to.throw(RangeError);
    expect(() => decodeParameter("uint256", "0x1234")).to.throw(RangeError);
    expect(() => decodeParameter("uint256", "0x" + "1".repeat(63))).to.throw(/odd length/);
  });

  it("throws when a fixed array disagrees with its declared length", function () {
    // a real fixed array of two, read as three: the third head is missing
    const data = encode(["uint256[2]"], [[1n, 2n]]);
    expect(() => decodeParameter("uint256[3]", data)).to.throw(RangeError);
  });

  it("rejects unknown and malformed types", function () {
    expect(() => parseType("uint128")).to.throw(/unsupported/);
    expect(() => parseType("(uint256")).to.throw(/unbalanced/);
    expect(() => parseType("uint256[")).to.throw(/unbalanced/);
    expect(() => parseType("uint256,junk")).to.throw(/trailing/);
  });

  it("encodeParams still encodes and the decoder reads it back", function () {
    const data = encodeParams([{ type: "uint256", value: 5n }]);
    expect(decodeParameter("uint256", data)).to.equal(5n);
  });
});
