/**
 * @fix-author
 *   agent: Szamani AI
 *   timestamp: 2026-06-09T06:10:00Z
 *   test: #198 - DecodeParameter for dynamic types (string, bytes, arrays, tuples)
 *   runtime:
 *     os: linux
 *     arch: x64
 *     working_dir: /opt/projects/kraina
 *     shell: bash
 */

const {
  encodeUint256,
  encodeAddress,
  encodeBytes32,
  encodeBool,
  encodeString,
  encodeBytes,
  encodeArray,
  encodeParams,
  decodeHex,
  decodeUint256,
  decodeAddress,
  decodeBool,
  decodeString,
  decodeBytes,
  decodeDynamicArray,
  decodeStringArray,
  decodeTuple,
  decodeParameter,
  decodeParams,
  functionSelector,
  packCalldata,
} = require("../sdk/src/utils/encoding.ts" );

// Polyfill for ts-node / hardhat compatibility
let encoding;
try {
  encoding = require("../sdk/src/utils/encoding");
} catch {
  // If running via hardhat, ts-node may need to be registered
  encoding = {
    encodeUint256,
    encodeAddress,
    encodeBytes32,
    encodeBool,
    encodeString,
    encodeBytes,
    encodeArray,
    encodeParams,
    decodeHex,
    decodeUint256,
    decodeAddress,
    decodeBool,
    decodeString,
    decodeBytes,
    decodeDynamicArray,
    decodeStringArray,
    decodeTuple,
    decodeParameter,
    decodeParams,
    functionSelector,
    packCalldata,
  };
}

const { assert, expect } = require("chai");

function assertBufferEqual(actual, expected, msg) {
  assert.instanceOf(actual, Buffer, `${msg}: expected Buffer`);
  assert.strictEqual(
    actual.toString("hex"),
    Buffer.from(expected).toString("hex"),
    `${msg}: buffer content mismatch`
  );
}

describe("ABI Encoding - Dynamic Types (#198)", function () {
  // =========================================================
  // ENCODING
  // =========================================================

  describe("encodeUint256", function () {
    it("should encode a uint256 value to 64 hex chars", function () {
      const result = encoding.encodeUint256(42);
      assert.strictEqual(result.length, 64);
      assert.strictEqual(result, "000000000000000000000000000000000000000000000000000000000000002a");
    });

    it("should encode zero", function () {
      const result = encoding.encodeUint256(0);
      assert.strictEqual(result, "0".repeat(64));
    });

    it("should reject negative values", function () {
      assert.throws(() => encoding.encodeUint256(-1), /cannot be negative/);
    });

    it("should reject overflow values", function () {
      assert.throws(
        () => encoding.encodeUint256(2n ** 256n),
        /overflow/
      );
    });
  });

  describe("encodeAddress", function () {
    it("should encode an address to 64 hex chars", function () {
      const result = encoding.encodeAddress("0x1234");
      const expected = "0".repeat(60) + "1234";
      assert.strictEqual(result, expected);
    });

    it("should handle 0x prefix", function () {
      const with0x = encoding.encodeAddress("0xAbCd");
      const without = encoding.encodeAddress("AbCd");
      assert.strictEqual(with0x, without);
    });
  });

  describe("encodeString", function () {
    it("should encode a string with length prefix", function () {
      const result = encoding.encodeString("hello");
      // length=5, hex="68656c6c6f", padded to 32B
      assert.strictEqual(result.length, 128); // 64 (length) + 64 (data padded)
      assert.include(result, "0000000000000000000000000000000000000000000000000000000000000005");
      assert.include(result, "68656c6c6f");
    });
  });

  describe("encodeBytes", function () {
    it("should encode bytes with length prefix", function () {
      const result = encoding.encodeBytes("0xdeadbeef");
      assert.strictEqual(result.length, 128); // 64 (length) + 64 (data padded)
      assert.include(result, "deadbeef");
    });

    it("should handle bytes without 0x prefix", function () {
      const with0x = encoding.encodeBytes("0xabcd");
      const without = encoding.encodeBytes("abcd");
      assert.strictEqual(with0x, without);
    });
  });

  describe("encodeBool", function () {
    it("should encode true", function () {
      assert.strictEqual(
        encoding.encodeBool(true),
        "0000000000000000000000000000000000000000000000000000000000000001"
      );
    });

    it("should encode false", function () {
      assert.strictEqual(
        encoding.encodeBool(false),
        "0000000000000000000000000000000000000000000000000000000000000000"
      );
    });
  });

  describe("encodeParams", function () {
    it("should encode static params without head/tail offset", function () {
      const result = encoding.encodeParams([
        { type: "uint256", value: 42 },
        { type: "address", value: "0x1234" },
      ]);
      assert.strictEqual(result.startsWith("0x"), true);
      // uint256 42 = 2a
      assert.include(result, "2a");
    });

    it("should encode mixed static+dynamic params with proper offsets", function () {
      const result = encoding.encodeParams([
        { type: "uint256", value: 1 },
        { type: "string", value: "hello" },
      ]);
      assert.strictEqual(result.startsWith("0x"), true);
      // First 64 hex chars: uint256 1 = on
      // Next 64 hex chars: offset pointer for string = 32 = 20 hex = at position 64
      assert.include(result, "1".padStart(64, "0"));
    });
  });

  // =========================================================
  // DECODING
  // =========================================================

  describe("decodeUint256", function () {
    it("should decode a padded hex slot", function () {
      const result = encoding.decodeUint256(
        "0x000000000000000000000000000000000000000000000000000000000000002a"
      );
      assert.strictEqual(result, 42n);
    });

    it("should handle short values with left-padding", function () {
      const result = encoding.decodeUint256("0x2a");
      assert.strictEqual(result, 42n);
    });

    it("should handle slot without 0x prefix", function () {
      const result = encoding.decodeUint256("2a");
      assert.strictEqual(result, 42n);
    });
  });

  describe("decodeAddress", function () {
    it("should decode the last 20 bytes as address", function () {
      const result = encoding.decodeAddress(
        "0x000000000000000000000000abcedef1234567890123456789012345678901234"
      );
      assert.strictEqual(result, "0x" + "abcedef1234567890123456789012345678901234".toLowerCase());
    });
  });

  describe("decodeBool", function () {
    it("should decode true", function () {
      assert.strictEqual(encoding.decodeBool("0x1"), true);
    });

    it("should decode false", function () {
      assert.strictEqual(encoding.decodeBool("0x0"), false);
    });
  });

  describe("decodeString", function () {
    it("should decode a string with offset pointer", function () {
      // Data layout: offset ptr at byte 0 pointing to byte 32, then length=5, then "hello"
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000020" + // offset=32
        "0000000000000000000000000000000000000000000000000000000000000005" + // length=5
        "68656c6c6f000000000000000000000000000000000000000000000000000000"; // "hello" padded
      const result = encoding.decodeString(data, 0);
      assert.strictEqual(result, "hello");
    });

    it("should handle empty string", function () {
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000020" +
        "0000000000000000000000000000000000000000000000000000000000000000" +
        "0000000000000000000000000000000000000000000000000000000000000000";
      const result = encoding.decodeString(data, 0);
      assert.strictEqual(result, "");
    });
  });

  describe("decodeBytes", function () {
    it("should decode bytes as Buffer", function () {
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000020" + // offset=32
        "0000000000000000000000000000000000000000000000000000000000000004" + // length=4
        "deadbeef00000000000000000000000000000000000000000000000000000000"; // data=deadbeef padded
      const result = encoding.decodeBytes(data, 0);
      assertBufferEqual(result, Buffer.from("deadbeef", "hex"), "decodeBytes");
    });
  });

  describe("decodeDynamicArray", function () {
    it("should decode a uint256 dynamic array", function () {
      // Array of [1, 2, 3]
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000020" + // offset=32
        "0000000000000000000000000000000000000000000000000000000000000003" + // length=3
        "0000000000000000000000000000000000000000000000000000000000000001" + // 1
        "0000000000000000000000000000000000000000000000000000000000000002" + // 2
        "0000000000000000000000000000000000000000000000000000000000000003"; // 3
      const result = encoding.decodeDynamicArray(data, 0, encoding.decodeUint256);
      assert.deepStrictEqual(result, [1n, 2n, 3n]);
    });
  });

  describe("decodeStringArray", function () {
    it("should decode an array of strings", function () {
      // Array of ["hello", "world"]
      // Head: [offset_to_array]
      // Array: [length=2, offset_to_elem0, offset_to_elem1]
      // elem0 at position: data_start + arr_offsets[0]
      // elem1 at position: data_start + arr_offsets[1]
      // Offset calculation:
      // - array starts at byte 32 (after the head offset pointer)
      // - array has: length (32B) + 2 offset pointers (64B) = 96B = 192 hex chars
      // - elem0 starts at byte 32 + (offset of elem0) = follows right after the array's data after its own offset pointers
      // Let's do it manually:
      // First compute offsets: array starts at byte 32
      // Array data starts at byte 32 in the data hex string
      // Inside array: length(32B) at pos 64, offset0(32B) at pos 96, offset1(32B) at pos 128
      // offset0 = 64 means byte 32 + 64 = byte 96 from data start = position 192 in hex
      // offset1 = 96 means byte 32 + 96 = byte 128 from data start = position 256 in hex

      // Actually let me construct this more carefully
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000020" + // head: offset to array = 32
        "0000000000000000000000000000000000000000000000000000000000000002" + // array length = 2
        "0000000000000000000000000000000000000000000000000000000000000040" + // offset to elem0 = 64
        "0000000000000000000000000000000000000000000000000000000000000080" + // offset to elem1 = 128
        "0000000000000000000000000000000000000000000000000000000000000005" + // elem0 length = 5
        "68656c6c6f000000000000000000000000000000000000000000000000000000" + // "hello"
        "0000000000000000000000000000000000000000000000000000000000000005" + // elem1 length = 5
        "776f726c64000000000000000000000000000000000000000000000000000000"; // "world"
      const result = encoding.decodeStringArray(data, 0);
      assert.deepStrictEqual(result, ["hello", "world"]);
    });
  });

  describe("decodeTuple - Nested Recursive", function () {
    it("should decode a flat tuple with uint, string, bool", function () {
      // Tuple: {amount: uint256, name: string, active: bool}
      // Static head: [amount(32B), offset_to_name(32B), active(32B)]
      // tail: [length(32B), "name" data padded(32B)]
      const data =
        "0x" +
        "000000000000000000000000000000000000000000000000000000000000002a" + // amount=42
        "0000000000000000000000000000000000000000000000000000000000000060" + // offset to name = 96
        "0000000000000000000000000000000000000000000000000000000000000001" + // active=true
        "0000000000000000000000000000000000000000000000000000000000000004" + // name length=4
        "7465737400000000000000000000000000000000000000000000000000000000"; // "test"

      const result = encoding.decodeTuple(data, [
        { name: "amount", type: "uint256" },
        { name: "name", type: "string" },
        { name: "active", type: "bool" },
      ]);

      assert.strictEqual(result.amount, 42n);
      assert.strictEqual(result.name, "test");
      assert.strictEqual(result.active, true);
    });

    it("should decode a nested tuple recursively", function () {
      // Outer tuple: {value: uint256, inner: tuple(data: bytes, flag: bool)}
      // This requires nested tuple decoding
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000001" + // value=1
        "0000000000000000000000000000000000000000000000000000000000000040" + // offset to inner = 64
        "0000000000000000000000000000000000000000000000000000000000000040" + // inner.data offset = 64 (from inner start)
        "0000000000000000000000000000000000000000000000000000000000000001" + // inner.flag = true
        "0000000000000000000000000000000000000000000000000000000000000002" + // inner.data length = 2
        "abcd000000000000000000000000000000000000000000000000000000000000"; // inner.data = 0xabcd

      const result = encoding.decodeTuple(data, [
        { name: "value", type: "uint256" },
        {
          name: "inner",
          type: "tuple",
          components: [
            { name: "data", type: "bytes" },
            { name: "flag", type: "bool" },
          ],
        },
      ]);

      assert.strictEqual(result.value, 1n);
      assert.instanceOf(result.inner, Object);
      assertBufferEqual(result.inner.data, Buffer.from("abcd", "hex"), "nested tuple bytes");
      assert.strictEqual(result.inner.flag, true);
    });

    it("should decode a tuple with dynamic array", function () {
      // {values: uint256[], name: string}
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000040" + // offset to values = 64
        "0000000000000000000000000000000000000000000000000000000000000080" + // offset to name = 128
        "0000000000000000000000000000000000000000000000000000000000000003" + // values length = 3
        "0000000000000000000000000000000000000000000000000000000000000001" + // values[0] = 1
        "0000000000000000000000000000000000000000000000000000000000000002" + // values[1] = 2
        "0000000000000000000000000000000000000000000000000000000000000003" + // values[2] = 3
        "0000000000000000000000000000000000000000000000000000000000000005" + // name length = 5
        "68656c6c6f000000000000000000000000000000000000000000000000000000"; // "hello"

      const result = encoding.decodeTuple(data, [
        { name: "values", type: "uint256[]" },
        { name: "name", type: "string" },
      ]);

      assert.deepStrictEqual(result.values, [1n, 2n, 3n]);
      assert.strictEqual(result.name, "hello");
    });
  });

  describe("decodeParameter - Unified API", function () {
    it("should decode uint256", function () {
      const data =
        "0x" +
        "000000000000000000000000000000000000000000000000000000000000002a";
      const result = encoding.decodeParameter(data, "uint256", 0);
      assert.strictEqual(result, 42n);
    });

    it("should decode string", function () {
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000020" +
        "0000000000000000000000000000000000000000000000000000000000000005" +
        "68656c6c6f000000000000000000000000000000000000000000000000000000";
      const result = encoding.decodeParameter(data, "string", 0);
      assert.strictEqual(result, "hello");
    });

    it("should decode bytes as Buffer", function () {
      const data =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000020" +
        "0000000000000000000000000000000000000000000000000000000000000002" +
        "abcd000000000000000000000000000000000000000000000000000000000000";
      const result = encoding.decodeParameter(data, "bytes", 0);
      assert.instanceOf(result, Buffer);
      assert.strictEqual(result.toString("hex"), "abcd");
    });
  });

  describe("decodeParams - Batch API", function () {
    it("should decode multiple params", function () {
      // ABI-encoded: uint256=42, string="hello"
      const data =
        "0x" +
        "000000000000000000000000000000000000000000000000000000000000002a" + // uint256 42
        "0000000000000000000000000000000000000000000000000000000000000040" + // offset to string = 64
        "0000000000000000000000000000000000000000000000000000000000000005" + // string length = 5
        "68656c6c6f000000000000000000000000000000000000000000000000000000"; // "hello"
      const result = encoding.decodeParams(data, ["uint256", "string"]);
      assert.strictEqual(result[0], 42n);
      assert.strictEqual(result[1], "hello");
    });
  });

  // =========================================================
  // COMPLEX ACCEPTANCE CRITERIA TEST
  // =========================================================

  describe("Acceptance Criteria - Complex Return Type (string + uint256[] + uint256)", function () {
    it("should decode a complex return type with string, array, and uint", function () {
      // Simulating a contract function returning: (string, uint256[], uint256)
      // Decode the entire return data
      const returnData =
        "0x" +
        "0000000000000000000000000000000000000000000000000000000000000060" + // offset to string = 96
        "00000000000000000000000000000000000000000000000000000000000000a0" + // offset to array = 160
        "000000000000000000000000000000000000000000000000000000000000002a" + // uint = 42
        "0000000000000000000000000000000000000000000000000000000000000005" + // string length = 5
        "68656c6c6f000000000000000000000000000000000000000000000000000000" + // "hello"
        "0000000000000000000000000000000000000000000000000000000000000003" + // array length = 3
        "0000000000000000000000000000000000000000000000000000000000000001" + // [0] = 1
        "0000000000000000000000000000000000000000000000000000000000000002" + // [1] = 2
        "0000000000000000000000000000000000000000000000000000000000000003"; // [2] = 3

      // First, decode using the tuple API
      const result = encoding.decodeTuple(returnData, [
        { name: "name", type: "string" },
        { name: "values", type: "uint256[]" },
        { name: "total", type: "uint256" },
      ]);

      assert.strictEqual(result.name, "hello", "string should decode to 'hello'");
      assert.deepStrictEqual(
        result.values,
        [1n, 2n, 3n],
        "array should decode to [1n, 2n, 3n]"
      );
      assert.strictEqual(result.total, 42n, "uint should decode to 42");
    });
  });

  // =========================================================
  // FUNCTIONS THAT USE Dynamic TYPES
  // =========================================================

  describe("backward compatibility", function () {
    it("decodeUint256 should handle both padded and short slots", function () {
      assert.strictEqual(encoding.decodeUint256("0x2a"), 42n);
      assert.strictEqual(
        encoding.decodeUint256(
          "0x000000000000000000000000000000000000000000000000000000000000002a"
        ),
        42n
      );
    });

    it("original decodeHex should still work", function () {
      assert.strictEqual(encoding.decodeHex("0xff"), 255n);
    });

    it("encodeUint256 should still work for old callers", function () {
      const result = encoding.encodeUint256(42);
      assert.strictEqual(result.length, 64);
    });

    it("functionSelector should produce 4-byte selector", function () {
      const result = encoding.functionSelector("transfer(address,uint256)");
      assert.strictEqual(result.length, 10); // 0x + 8 hex chars
      assert.strictEqual(result.startsWith("0x"), true);
    });
  });
});
