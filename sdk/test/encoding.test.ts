/**
 * Comprehensive tests for ABI encoding/decoding utilities.
 * Covers all acceptance criteria from issue #198.
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
  decodeHex,
} from "../src/utils/encoding";

describe("encodeUint256", () => {
  it("encodes a small number", () => {
    expect(encodeUint256(42)).toBe("0".repeat(62) + "2a");
  });
  it("throws on overflow", () => {
    expect(() => encodeUint256(1n << 256n)).toThrow();
  });
});

describe("decodeParameter - static types", () => {
  it("decodes uint256", () => {
    const hex = "0x" + "0".repeat(63) + "2a";
    expect(decodeParameter(hex, "uint256")).toBe(42n);
  });
  it("decodes bool", () => {
    expect(decodeParameter("0x" + "0".repeat(63) + "1", "bool")).toBe(true);
  });
});

describe("decodeParameter - string", () => {
  it("decodes string to JS string", () => {
    const encoded = "0x" + "0".repeat(63) + "20" + "0".repeat(63) + "5" + Buffer.from("hello", "utf8").toString("hex").padEnd(64, "0");
    expect(decodeParameter(encoded, "string")).toBe("hello");
  });
});

describe("decodeParameter - bytes", () => {
  it("decodes bytes to Uint8Array", () => {
    const encoded = "0x" + "0".repeat(63) + "20" + "0".repeat(63) + "4" + "deadbeef".padEnd(64, "0");
    const result = decodeParameter(encoded, "bytes") as Uint8Array;
    expect(result).toBeInstanceOf(Uint8Array);
    expect(result.length).toBe(4);
  });
});

describe("decodeParameter - dynamic arrays", () => {
  it("decodes uint256[]", () => {
    const encoded = "0x" + "0".repeat(63) + "20" + "0".repeat(63) + "3" + "0".repeat(63) + "a" + "0".repeat(63) + "14" + "0".repeat(63) + "1e";
    const result = decodeParameter(encoded, "uint256[]") as bigint[];
    expect(result).toHaveLength(3);
    expect(result[0]).toBe(10n);
  });
});

describe("decodeParameter - tuples", () => {
  it("decodes static tuple", () => {
    const encoded = "0x" + "0".repeat(63) + "2a" + "0".repeat(63) + "1";
    const result = decodeParameter(encoded, "tuple(uint256,bool)") as Record<string, unknown>;
    expect(result).toHaveProperty("member0", 42n);
    expect(result).toHaveProperty("member1", true);
  });

  it("decodes tuple with dynamic member", () => {
    const encoded = "0x" + "0".repeat(63) + "2a" + "0".repeat(62) + "40" + "0".repeat(63) + "2" + Buffer.from("hi", "utf8").toString("hex").padEnd(64, "0");
    const result = decodeParameter(encoded, "tuple(uint256,string)") as Record<string, unknown>;
    expect(result.member0).toBe(42n);
    expect(result.member1).toBe("hi");
  });

  it("decodes nested tuple recursively", () => {
    const addr = "b".repeat(40);
    const encoded = "0x" + "0".repeat(63) + "7b" + "0".repeat(63) + "1" + "0".repeat(24) + addr;
    const result = decodeParameter(encoded, "tuple(uint256,tuple(bool,address))") as Record<string, unknown>;
    expect(result.member0).toBe(123n);
    const inner = result.member1 as Record<string, unknown>;
    expect(inner.member0).toBe(true);
    expect(inner.member1).toBe("0x" + addr);
  });
});

describe("Complex return: string + array + uint", () => {
  it("decodes complex tuple", () => {
    const strHex = Buffer.from("test", "utf8").toString("hex").padEnd(64, "0");
    const encoded = "0x" + "0".repeat(62) + "60" + "0".repeat(62) + "c0" + "0".repeat(63) + "63" + "0".repeat(63) + "4" + strHex + "0".repeat(63) + "2" + "0".repeat(63) + "1" + "0".repeat(63) + "2";
    const result = decodeParameter(encoded, "tuple(string,uint256[],uint256)") as Record<string, unknown>;
    expect(result.member0).toBe("test");
    const arr = result.member1 as bigint[];
    expect(arr).toHaveLength(2);
    expect(arr[0]).toBe(1n);
    expect(arr[1]).toBe(2n);
    expect(result.member2).toBe(99n);
  });
});

describe("decodeParams", () => {
  it("decodes multiple static types", () => {
    const hex = "0x" + "0".repeat(63) + "2a" + "0".repeat(24) + "1234567890abcdef1234567890abcdef12345678" + "0".repeat(63) + "1";
    const result = decodeParams(hex, ["uint256", "address", "bool"]);
    expect(result[0]).toBe(42n);
    expect(result[2]).toBe(true);
  });
});

describe("encodeParams with dynamic types", () => {
  it("roundtrips string+uint", () => {
    const encoded = encodeParams([
      { type: "string", value: "world" },
      { type: "uint256", value: 99 },
    ]);
    const decoded = decodeParams(encoded, ["string", "uint256"]);
    expect(decoded[0]).toBe("world");
    expect(decoded[1]).toBe(99n);
  });
});

describe("Error cases", () => {
  it("throws on unsupported type", () => {
    expect(() => decodeParameter("0x00", "foo")).toThrow();
  });
});
