/**
 * Tests for ABI encoding/decoding utilities — decodeParameter + decodeParams dynamic types.
 */
import {
  encodeUint256,
  encodeAddress,
  encodeString,
  encodeDynamicBytes,
  encodeParams,
  decodeParameter,
  decodeParams,
  decodeUint256,
  decodeAddress,
  decodeBool,
} from "../src/utils/encoding";

describe("encodeUint256", () => {
  it("encodes a number", () => {
    expect(encodeUint256(42)).toBe("0".repeat(62) + "2a");
  });

  it("encodes max uint256", () => {
    const max = (1n << 256n) - 1n;
    expect(encodeUint256(max)).toBe("f".repeat(64));
  });
});

describe("encodeAddress", () => {
  it("encodes an address", () => {
    const result = encodeAddress("0x1234567890abcdef1234567890abcdef12345678");
    expect(result.slice(-40)).toBe("1234567890abcdef1234567890abcdef12345678");
  });
});

describe("encodeString", () => {
  it("encodes a short string", () => {
    const result = encodeString("hello");
    expect(result.length).toBeGreaterThanOrEqual(128);
    expect(result.slice(0, 64)).toBe("0".repeat(63) + "5");
  });
});

describe("decodeUint256", () => {
  it("decodes a uint256", () => {
    const hex = "0x" + "0".repeat(63) + "1";
    expect(decodeUint256(hex)).toBe(1n);
  });

  it("decodes short hex", () => {
    expect(decodeUint256("ff")).toBe(255n);
  });
});

describe("decodeAddress", () => {
  it("decodes an address", () => {
    const slot = "0".repeat(24) + "1234567890abcdef1234567890abcdef12345678";
    expect(decodeAddress(slot)).toBe("0x1234567890abcdef1234567890abcdef12345678");
  });
});

describe("decodeBool", () => {
  it("decodes true", () => {
    expect(decodeBool("0x" + "0".repeat(63) + "1")).toBe(true);
  });

  it("decodes false", () => {
    expect(decodeBool("0x" + "0".repeat(64))).toBe(false);
  });
});

describe("decodeParameter", () => {
  it("decodes uint256 static", () => {
    const hex = "0x" + "0".repeat(63) + "2a";
    expect(decodeParameter("uint256", hex)).toBe(42n);
  });

  it("decodes address static", () => {
    const addr = "1234567890abcdef1234567890abcdef12345678";
    const hex = "0x" + "0".repeat(24) + addr;
    expect(decodeParameter("address", hex)).toBe("0x" + addr);
  });

  it("decodes bool static true", () => {
    const hex = "0x" + "0".repeat(63) + "1";
    expect(decodeParameter("bool", hex)).toBe(true);
  });

  it("decodes bool static false", () => {
    const hex = "0x" + "0".repeat(64);
    expect(decodeParameter("bool", hex)).toBe(false);
  });

  it("decodes bytes32 static", () => {
    const data = "aa".repeat(32);
    expect(decodeParameter("bytes32", "0x" + data)).toBe("0x" + data);
  });

  it("throws on unsupported type", () => {
    expect(() => decodeParameter("tuple", "0x00")).toThrow();
  });
});

describe("decodeParams", () => {
  it("decodes multiple static types", () => {
    const hex = "0x" +
      "0".repeat(63) + "2a" +
      "0".repeat(24) + "1234567890abcdef1234567890abcdef12345678" +
      "0".repeat(63) + "1";
    const result = decodeParams(["uint256", "address", "bool"], hex);
    expect(result[0]).toBe(42n);
    expect(result[2]).toBe(true);
  });

  it("decodes mixed static types", () => {
    const hex = "0x" +
      "0".repeat(63) + "1" +
      "0".repeat(64);
    const result = decodeParams(["bool", "bool"], hex);
    expect(result[0]).toBe(true);
    expect(result[1]).toBe(false);
  });
});

describe("encodeParams with dynamic types", () => {
  it("encodes string params", () => {
    const result = encodeParams([
      { type: "uint256", value: 42 },
      { type: "string", value: "hello" },
    ]);
    expect(result.startsWith("0x")).toBe(true);
    expect(result.length).toBeGreaterThan(130);
  });
});
