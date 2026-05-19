import { describe, it, expect } from "vitest";
import { encodeUint256, encodeInt256, encodeAddress, decodeHex, decodeInt256 } from "./encoding";

describe("ABI Encoding", () => {
  it("should throw on uint256 overflow", () => {
    const huge = (1n << 256n);
    expect(() => encodeUint256(huge)).toThrow("uint256 out of range");
  });

  it("should throw on negative uint256", () => {
    expect(() => encodeUint256(-1n)).toThrow("uint256 out of range");
  });

  it("should encode int256 negative values in two's complement", () => {
    // -1 in 256-bit hex is 64 'f's
    const encoded = encodeInt256(-1n);
    expect(encoded).toBe("f".repeat(64));
  });

  it("should decode int256 negative values correctly", () => {
    const slot = "f".repeat(64);
    expect(decodeInt256(slot)).toBe(-1n);
  });

  it("should throw on missing 0x prefix for address", () => {
    expect(() => encodeAddress("1234567890123456789012345678901234567890")).toThrow("missing 0x");
  });

  it("should throw on invalid hex in decodeHex", () => {
    expect(() => decodeHex("123")).toThrow("must start with 0x");
  });
});
