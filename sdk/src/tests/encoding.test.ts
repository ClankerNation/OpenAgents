import { describe, it, expect } from "vitest";
import {
  decodeParameter,
  decodeUint256,
  decodeAddress,
  decodeBool,
  encodeUint256,
  encodeAddress,
  encodeBool,
  encodeParams,
} from "../utils/encoding";

describe("decodeParameter", () => {
  it("decodes uint256", () => {
    const hex = "0x00000000000000000000000000000000000000000000000000000000000000ff";
    expect(decodeParameter(hex, "uint256")).toBe(255n);
  });

  it("decodes address", () => {
    const hex = "0x0000000000000000000000004bbeeb066ed09b7aed07bf39eee0460dfa261520";
    expect(decodeParameter(hex, "address")).toBe("0x4bbeeb066ed09b7aed07bf39eee0460dfa261520");
  });

  it("decodes bool true", () => {
    const hex = "0x0000000000000000000000000000000000000000000000000000000000000001";
    expect(decodeParameter(hex, "bool")).toBe(true);
  });

  it("decodes bool false", () => {
    const hex = "0x0000000000000000000000000000000000000000000000000000000000000000";
    expect(decodeParameter(hex, "bool")).toBe(false);
  });

  it("decodes string", () => {
    // offset = 0x20 (32 bytes), length = 0x05 (5 bytes), "hello" = 68656c6c6f
    const hex =
      "0000000000000000000000000000000000000000000000000000000000000020" +
      "0000000000000000000000000000000000000000000000000000000000000005" +
      "68656c6c6f000000000000000000000000000000000000000000000000000000";
    expect(decodeParameter("0x" + hex, "string")).toBe("hello");
  });

  it("decodes bytes", () => {
    // offset = 0x20, length = 0x03, deadbeef = deadbeef
    const hex =
      "0000000000000000000000000000000000000000000000000000000000000020" +
      "0000000000000000000000000000000000000000000000000000000000000003" +
      "deadbeef00000000000000000000000000000000000000000000000000000000";
    const result = decodeParameter("0x" + hex, "bytes");
    expect(result).toBeInstanceOf(Uint8Array);
    expect(Array.from(result as Uint8Array)).toEqual([0xde, 0xad, 0xbe, 0xef]);
  });

  it("decodes uint256 array", () => {
    // offset = 0x20, length = 2, values = [1, 2]
    const hex =
      "0000000000000000000000000000000000000000000000000000000000000020" +
      "0000000000000000000000000000000000000000000000000000000000000002" +
      "0000000000000000000000000000000000000000000000000000000000000001" +
      "0000000000000000000000000000000000000000000000000000000000000002";
    const result = decodeParameter("0x" + hex, "uint256[]") as bigint[];
    expect(result).toEqual([1n, 2n]);
  });

  it("decodes address array", () => {
    // offset = 0x20, length = 1
    const addr = "4bbeeb066ed09b7aed07bf39eee0460dfa261520";
    const hex =
      "0000000000000000000000000000000000000000000000000000000000000020" +
      "0000000000000000000000000000000000000000000000000000000000000001" +
      "000000000000000000000000" + addr;
    const result = decodeParameter("0x" + hex, "address[]") as string[];
    expect(result).toEqual(["0x" + addr]);
  });

  it("throws on unsupported type", () => {
    expect(() => decodeParameter("0x00", "tuple")).toThrow("Unsupported type");
  });
});

describe("encode/decode roundtrip", () => {
  it("roundtrips uint256", () => {
    const encoded = encodeUint256(12345n);
    const decoded = decodeUint256(encoded);
    expect(decoded).toBe(12345n);
  });

  it("roundtrips address", () => {
    const addr = "0x4bbeeb066ed09b7aed07bf39eee0460dfa261520";
    const encoded = encodeAddress(addr);
    const decoded = decodeAddress(encoded);
    expect(decoded).toBe(addr.toLowerCase());
  });

  it("roundtrips bool", () => {
    const encodedTrue = encodeBool(true);
    const encodedFalse = encodeBool(false);
    expect(decodeBool(encodedTrue)).toBe(true);
    expect(decodeBool(encodedFalse)).toBe(false);
  });
});
