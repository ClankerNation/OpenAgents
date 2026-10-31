import { describe, it } from 'node:test';
import assert from 'node:assert';
import {
  encodeUint256, encodeAddress, encodeBool, encodeParams,
  decodeHex, decodeUint256, decodeAddress, decodeBool,
  decodeString, decodeBytes, decodeParameter, decodeDynamicArray,
} from '../src/utils/encoding.ts';

describe('encoding.ts', () => {
  describe('encodeUint256', () => {
    it('encodes small values', () => {
      assert.strictEqual(encodeUint256(42), '0'.repeat(62) + '2a');
    });

    it('encodes zero', () => {
      assert.strictEqual(encodeUint256(0), '0'.repeat(64));
    });

    it('throws on overflow', () => {
      assert.throws(() => encodeUint256(2n ** 256n), /out of range/);
    });

    it('throws on negative', () => {
      assert.throws(() => encodeUint256(-1), /out of range/);
    });
  });

  describe('encodeAddress', () => {
    it('encodes valid address', () => {
      const addr = '0x' + 'a'.repeat(40);
      assert.strictEqual(encodeAddress(addr), 'a'.repeat(40).padStart(64, '0'));
    });

    it('throws on invalid length', () => {
      assert.throws(() => encodeAddress('0x1234'), /Invalid address/);
    });
  });

  describe('encodeBool', () => {
    it('encodes true', () => {
      assert.strictEqual(encodeBool(true), '1'.padStart(64, '0'));
    });

    it('encodes false', () => {
      assert.strictEqual(encodeBool(false), '0'.repeat(64));
    });
  });

  describe('decodeHex', () => {
    it('parses hex with 0x prefix', () => {
      assert.strictEqual(decodeHex('0xff'), 255n);
    });

    it('parses hex without 0x prefix', () => {
      assert.strictEqual(decodeHex('ff'), 255n);
    });

    it('throws on invalid hex', () => {
      assert.throws(() => decodeHex('0xgg'), /Invalid hex/);
    });
  });

  describe('decodeUint256', () => {
    it('pads short values', () => {
      assert.strictEqual(decodeUint256('2a'), 42n);
    });

    it('handles full 64-char slot', () => {
      assert.strictEqual(decodeUint256('0'.repeat(63) + '2a'), 42n);
    });
  });

  describe('decodeAddress', () => {
    it('extracts last 20 bytes', () => {
      const slot = '0'.repeat(24) + 'a'.repeat(40);
      assert.strictEqual(decodeAddress(slot), '0x' + 'a'.repeat(40));
    });
  });

  describe('decodeBool', () => {
    it('decodes true', () => {
      assert.strictEqual(decodeBool('1'), true);
    });

    it('decodes false', () => {
      assert.strictEqual(decodeBool('0'), false);
    });
  });

  describe('decodeString', () => {
    it('decodes a simple string', () => {
      // "hello" = offset 32, length 5, data
      const hello = Buffer.from('hello').toString('hex');
      const data = '0'.repeat(62) + '20' + // offset = 32
                  '0'.repeat(62) + '05' + // length = 5
                  hello.padEnd(64, '0');    // data
      const result = decodeString('0x' + data);
      assert.strictEqual(result, 'hello');
    });
  });

  describe('decodeBytes', () => {
    it('decodes bytes', () => {
      const bytes = 'aabbcc';
      const data = '0'.repeat(62) + '20' + // offset = 32
                  '0'.repeat(62) + '03' + // length = 3
                  bytes.padEnd(64, '0');   // data
      const result = decodeBytes('0x' + data);
      assert.strictEqual(result, '0xaabbcc');
    });
  });

  describe('decodeDynamicArray', () => {
    it('decodes uint256 array', () => {
      // [1, 2, 3]
      const data = '0'.repeat(62) + '20' + // offset = 32
                  '0'.repeat(62) + '03' + // length = 3
                  '0'.repeat(62) + '01' + // 1
                  '0'.repeat(62) + '02' + // 2
                  '0'.repeat(62) + '03';  // 3
      const result = decodeDynamicArray('0x' + data, 0, 'uint256');
      assert.deepStrictEqual(result, [1n, 2n, 3n]);
    });
  });

  describe('decodeParameter', () => {
    it('decodes uint256', () => {
      assert.strictEqual(decodeParameter('uint256', '0x' + '0'.repeat(62) + '2a'), 42n);
    });

    it('decodes address', () => {
      const slot = '0'.repeat(24) + 'a'.repeat(40);
      assert.strictEqual(decodeParameter('address', '0x' + slot), '0x' + 'a'.repeat(40));
    });

    it('decodes bool', () => {
      assert.strictEqual(decodeParameter('bool', '0x' + '0'.repeat(62) + '01'), true);
    });
  });

  describe('encodeParams', () => {
    it('encodes mixed params', () => {
      const result = encodeParams([
        { type: 'uint256', value: 42 },
        { type: 'bool', value: true },
      ]);
      assert.ok(result.startsWith('0x'));
      assert.ok(result.length > 2);
    });
  });
});
