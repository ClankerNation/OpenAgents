/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
import { expect } from "chai";
import { decodeString, decodeBytes, decodeArray, decodeTuple } from "../src/utils/encoding";

describe("Encoding Dynamic Types", function () {
  it("should decode a dynamic string", async function () {
    const encoded = "0x" +
      "0000000000000000000000000000000000000000000000000000000000000020" +
      "0000000000000000000000000000000000000000000000000000000000000005" +
      "68656c6c6f000000000000000000000000000000000000000000000000000000";
    
    const result = decodeString(encoded, 0);
    expect(result).to.equal("hello");
  });

  it("should decode dynamic bytes", async function () {
    const encoded = "0x" +
      "0000000000000000000000000000000000000000000000000000000000000020" +
      "0000000000000000000000000000000000000000000000000000000000000003" +
      "deadbeef00000000000000000000000000000000000000000000000000000000";
    
    const result = decodeBytes(encoded, 0);
    expect(result).to.be.instanceOf(Uint8Array);
    expect(result.length).to.equal(3);
    expect(result[0]).to.equal(0xde);
    expect(result[1]).to.equal(0xad);
    expect(result[2]).to.equal(0xbe);
  });

  it("should decode a dynamic array of uint256", async function () {
    const encoded = "0x" +
      "0000000000000000000000000000000000000000000000000000000000000020" +
      "0000000000000000000000000000000000000000000000000000000000000002" +
      "000000000000000000000000000000000000000000000000000000000000000a" +
      "0000000000000000000000000000000000000000000000000000000000000014";
    
    const result = decodeArray(encoded, "uint256", 0);
    expect(result.length).to.equal(2);
    expect(result[0]).to.equal(10n);
    expect(result[1]).to.equal(20n);
  });

  it("should decode a tuple with mixed types", async function () {
    const encoded = "0x" +
      "000000000000000000000000000000000000000000000000000000000000002a" +
      "0000000000000000000000000000000000000000000000000000000000000040" +
      "0000000000000000000000000000000000000000000000000000000000000003" +
      "6162630000000000000000000000000000000000000000000000000000000000";
    
    const result = decodeTuple(encoded, ["uint256", "string"]);
    expect(result[0]).to.equal(42n);
    expect(result[1]).to.equal("abc");
  });
});
