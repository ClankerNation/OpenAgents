/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
import { expect } from "chai";
import { 
  encodeUint256, 
  encodeInt256, 
  decodeHex, 
  decodeUint256, 
  decodeInt256 
} from "../src/utils/encoding";

describe("ABI Encoding Bounds and Signed Integers", function () {
  it("should throw on uint256 overflow", function () {
    const overflow = (1n << 256n);
    expect(() => encodeUint256(overflow)).to.throw("value out of bounds");
  });

  it("should throw on negative uint256", function () {
    expect(() => encodeUint256(-1n)).to.throw("value out of bounds");
  });

  it("should encode and decode int256 correctly", function () {
    const positive = 12345n;
    const negative = -12345n;
    
    const encodedPos = encodeInt256(positive);
    const encodedNeg = encodeInt256(negative);
    
    expect(decodeInt256(encodedPos)).to.equal(positive);
    expect(decodeInt256(encodedNeg)).to.equal(negative);
  });

  it("should throw on missing 0x prefix for decodeHex", function () {
    expect(() => decodeHex("1234")).to.throw("missing 0x prefix");
  });

  it("should throw on missing 0x prefix for decodeUint256", function () {
    expect(() => decodeUint256("1234")).to.throw("missing 0x prefix");
  });

  it("should pad short values correctly in decodeUint256", function () {
    const shortHex = "0x1";
    expect(decodeUint256(shortHex)).to.equal(1n);
  });
});
