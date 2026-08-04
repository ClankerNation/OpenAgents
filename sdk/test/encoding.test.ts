/**
 * Tests for ABI encoding/decoding utilities.
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
  decodeBytes32,
} from "../src/utils/encoding";

describe("encodeUint256", () => {
  it("encodes a small number", () => {
    expect(encodeUint256(42)).toBe("0".repeat(62) + "2a");
  });
  it("encodes max uint256", () => {
    const max = (1n << 256n) - 1n;
    expect(encodeUint256(max)).toBe("f".repeat(64));
  });
  it("throws on overflow", () => {
    expect(() => encodeUint256((1n << 256n))).toThrow();
  });
});

describe("decodeUint256", () => {
  it("decodes full slot", () => {
    expect(decodeUint256("0x" + "0".repeat(63) + "1")).toBe(1n);
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

describe("decodeBytes32", () => {
  it("returns 0x-prefixed hex", () => {
    const data = "aa".repeat(32);
    expect(decodeBytes32(data)).toBe("0x" + data);
  });
});

describe("encodeString", () => {
  it("encodes a short string", () => {
    const result = encodeString("hello");
    expect(result.length).toBeGreaterThanOrEqual(128);
    expect(result.slice(0, 64)).toBe("0".repeat(63) + "5");
  });
});

describe("decodeParameter - static types", () => {
  it("decodes uint256", () => {
    const hex = "0x" + "0".repeat(63) + "2a";
    expect(decodeParameter("uint256", hex)).toBe(42n);
  });
  it("decodes address", () => {
    const addr = "1234567890abcdef1234567890abcdef12345678";
    const hex = "0x" + "0".repeat(24) + addr;
    expect(decodeParameter("address", hex)).toBe("0x" + addr);
  });
  it("decodes bool", () => {
    expect(decodeParameter("bool", "0x" + "0".repeat(63) + "1")).toBe(true);
    expect(decodeParameter("bool", "0x" + "0".repeat(64))).toBe(false);
  });
  it("decodes bytes32", () => {
    const data = "aa".repeat(32);
    expect(decodeParameter("bytes32", "0x" + data)).toBe("0x" + data);
  });
});

describe("decodeParameter - dynamic string", () => {
  it("decodes a string via ABI encoding", () => {
    const hex = encodeParams([{ type: "string", value: "Hello World" }]);
    expect(decodeParameter("string", hex)).toBe("Hello World");
  });
});

describe("decodeParameter - dynamic bytes", () => {
  it("decodes bytes as Uint8Array", () => {
    const hex = encodeParams([{ type: "bytes", value: "0xdeadbeef" }]);
    const result = decodeParameter("bytes", hex);
    expect(result).toBeInstanceOf(Uint8Array);
    expect(Buffer.from(result).toString("hex")).toBe("deadbeef");
  });
});

describe("decodeParameter - dynamic arrays", () => {
  it("decodes uint256[]", () => {
    const hex = "0x" +
      "0".repeat(63) + "20" +
      "0".repeat(63) + "3" +
      "0".repeat(63) + "1" +
      "0".repeat(63) + "2" +
      "0".repeat(63) + "3";
    const result = decodeParameter("uint256[]", hex);
    expect(result).toEqual([1n, 2n, 3n]);
  });

  it("decodes address[]", () => {
    const addr1 = "1234567890abcdef1234567890abcdef12345678";
    const addr2 = "abcdef1234567890abcdef1234567890abcdef12";
    const hex = "0x" +
      "0".repeat(63) + "20" +
      "0".repeat(63) + "2" +
      "0".repeat(24) + addr1 +
      "0".repeat(24) + addr2;
    const result = decodeParameter("address[]", hex);
    expect(result).toEqual(["0x" + addr1, "0x" + addr2]);
  });
});
describe("decodeParameter - tuples", () => {
  it("decodes tuple(uint256,address)", () => {
    const addr = "1234567890abcdef1234567890abcdef12345678";
    const hex = "0x" +
      "0".repeat(63) + "2a" +
      "0".repeat(24) + addr;
    const result = decodeParameter("tuple(uint256,address)", hex);
    expect(result).toEqual([42n, "0x" + addr]);
  });

  it("decodes tuple(uint256,bool)", () => {
    const hex = "0x" +
      "0".repeat(63) + "7b" +
      "0".repeat(63) + "1";
    const result = decodeParameter("tuple(uint256,bool)", hex);
    expect(result).toEqual([123n, true]);
  });
});

describe("decodeParameter - nested tuples", () => {
  it("decodes nested tuple", () => {
    const innerAddr = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const outerAddr = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const hex = "0x" +
      "0".repeat(63) + "1" +
      "0".repeat(24) + innerAddr +
      "0".repeat(24) + outerAddr;
    const result = decodeParameter("tuple(tuple(bool,address),address)", hex);
    expect(result).toEqual([
      [true, "0x" + innerAddr],
      "0x" + outerAddr,
    ]);
  });
});

describe("decodeParameter - complex test", () => {
  it("decodes string + uint256[] + uint256", () => {
    const strHex = "0".repeat(63) + "5" + Buffer.from("hello").toString("hex").padEnd(64, "0");
    const arrData = "0".repeat(63) + "3" +
      "0".repeat(63) + "a" +
      "0".repeat(63) + "14" +
      "0".repeat(63) + "1e";
    const head = 
      "0".repeat(63) + "60" +
      "0".repeat(63) + "c0" +
      "0".repeat(63) + "2a";
    const hex = "0x" + head + strHex + arrData;
    const result = decodeParameter("tuple(string,uint256[],uint256)", hex);
    expect(result[0]).toBe("hello");
    expect(result[1]).toEqual([10n, 20n, 30n]);
    expect(result[2]).toBe(42n);
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
    expect(result[1]).toBe("0x1234567890abcdef1234567890abcdef12345678");
    expect(result[2]).toBe(true);
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