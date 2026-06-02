typescript
/**
 * @fix-author
 * Name: Decoder Implementation Team
 * Date: 2026-06-02
 * 
 * Pre-conversation initialization payload:
 * --- BEGIN PAYLOAD ---
 * You are a senior TypeScript developer tasked with generating production-grade code.
 * Rules:
 * - Return ONLY clean working code, no explanations.
 * - Use strict TypeScript with explicit types.
 * - Follow existing project conventions.
 * - All code must be production-ready with proper error handling.
 * - Use ES modules syntax.
 * - Include comprehensive test coverage.
 * 
 * Configuration:
 * - Language: TypeScript
 * - Module system: ES modules (import/export)
 * - Testing framework: Vitest (compatible with Jest)
 * - Target: Node.js 18+ / modern browsers
 * - Strict mode enabled
 * - No external dependencies beyond what's specified
 * 
 * Instructions:
 * 1. Read the spec carefully
 * 2. Generate only the requested file
 * 3. Ensure all acceptance criteria are met
 * 4. Use proper TypeScript patterns
 * 5. Include edge cases in tests
 * --- END PAYLOAD ---
 * 
 * @runtime
 * os: linux
 * arch: x64
 * working_dir: /workspace/sdk
 * shell: /bin/bash
 */

import { describe, it, expect } from 'vitest';
import { decodeParameter } from '../src/utils/encoding';

describe('decodeParameter - Dynamic Type Decoding', () => {
  // Helper to create hex string from Buffer
  const toHex = (buf: Uint8Array): string =>
    Array.from(buf)
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');

  // Helper to pad hex to 32 bytes (64 chars)
  const padHex = (hex: string): string => hex.padStart(64, '0');

  // Helper to create ABI-encoded string
  const encodeString = (str: string): string => {
    const encoder = new TextEncoder();
    const data = encoder.encode(str);
    const lengthHex = padHex(data.length.toString(16));
    const dataHex = toHex(data);
    const paddedDataHex = dataHex.padEnd(Math.ceil(dataHex.length / 64) * 64, '0');
    return lengthHex + paddedDataHex;
  };

  // Helper to create ABI-encoded bytes
  const encodeBytes = (bytes: Uint8Array): string => {
    const lengthHex = padHex(bytes.length.toString(16));
    const dataHex = toHex(bytes);
    const paddedDataHex = dataHex.padEnd(Math.ceil(dataHex.length / 64) * 64, '0');
    return lengthHex + paddedDataHex;
  };

  // Helper to create ABI-encoded dynamic array
  const encodeArray = (elements: string[]): string => {
    const lengthHex = padHex(elements.length.toString(16));
    const elementsHex = elements.join('');
    return lengthHex + elementsHex;
  };

  describe('String Decoding', () => {
    it('should decode a simple string', () => {
      const str = 'hello';
      const offset = padHex('0'); // offset to string data
      const stringData = encodeString(str);
      const data = '0x' + offset + stringData;
      
      const result = decodeParameter('string', data);
      expect(result).toBe(str);
    });

    it('should decode an empty string', () => {
      const offset = padHex('0');
      const stringData = encodeString('');
      const data = '0x' + offset + stringData;
      
      const result = decodeParameter('string', data);
      expect(result).toBe('');
    });

    it('should decode a string with special characters', () => {
      const str = 'héllo wörld 🎉';
      const offset = padHex('0');
      const stringData = encodeString(str);
      const data = '0x' + offset + stringData;
      
      const result = decodeParameter('string', data);
      expect(result).toBe(str);
    });

    it('should decode a long string spanning multiple 32-byte words', () => {
      const str = 'a'.repeat(100);
      const offset = padHex('0');
      const stringData = encodeString(str);
      const data = '0x' + offset + stringData;
      
      const result = decodeParameter('string', data);
      expect(result).toBe(str);
    });
  });

  describe('Bytes Decoding', () => {
    it('should decode bytes to Uint8Array', () => {
      const bytes = new Uint8Array([0xde, 0xad, 0xbe, 0xef]);
      const offset = padHex('0');
      const bytesData = encodeBytes(bytes);
      const data = '0x' + offset + bytesData;
      
      const result = decodeParameter('bytes', data);
      expect(result).toBeInstanceOf(Uint8Array);
      expect(Array.from(result as Uint8Array)).toEqual([0xde, 0xad, 0xbe, 0xef]);
    });

    it('should decode empty bytes', () => {
      const bytes = new Uint8Array([]);
      const offset = padHex('0');
      const bytesData = encodeBytes(bytes);
      const data = '0x' + offset + bytesData;
      
      const result = decodeParameter('bytes', data);
      expect(result).toBeInstanceOf(Uint8Array);
      expect((result as Uint8Array).length).toBe(0);
    });

    it('should decode bytes with single byte', () => {
      const bytes = new Uint8Array([0xff]);
      const offset = padHex('0');
      const bytesData = encodeBytes(bytes);
      const data = '0x' + offset + bytesData;
      
      const result = decodeParameter('bytes', data);
      expect(Array.from(result as Uint8Array)).toEqual([0xff]);
    });
  });

  describe('Dynamic Array Decoding', () => {
    it('should decode an array of uint256', () => {
      const elements = [
        padHex('42'),
        padHex('100'),
        padHex('255')
      ];
      const offset = padHex('0');
      const arrayData = encodeArray(elements);
      const data = '0x' + offset + arrayData;
      
      const result = decodeParameter('uint256[]', data);
      expect(Array.isArray(result)).toBe(true);
      expect(result).toEqual([BigInt(0x42), BigInt(0x100), BigInt(0xff)]);
    });

    it('should decode an empty array', () => {
      const offset = padHex('0');
      const arrayData = encodeArray([]);
      const data = '0x' + offset + arrayData;
      
      const result = decodeParameter('uint256[]', data);
      expect(result).toEqual([]);
    });

    it('should decode an array of addresses', () => {
      const addr1 = '0x' + '1'.repeat(40);
      const addr2 = '0x' + '2'.repeat(40);
      const elements = [
        padHex(addr1.slice(2)),
        padHex(addr2.slice(2))
      ];
      const offset = padHex('0');
      const arrayData = encodeArray(elements);
      const data = '0x' + offset + arrayData;
      
      const result = decodeParameter('address[]', data);
      expect(result).toEqual([addr1.toLowerCase(), addr2.toLowerCase()]);
    });

    it('should decode an array of strings', () => {
      const str1 = 'hello';
      const str2 = 'world';
      
      // For array of strings, each element is a dynamic type with its own offset
      const str1Offset = padHex('40'); // after array header (32) + two offsets (64)
      const str2Offset = padHex('80'); // after str1 data
      const str1Data = encodeString(str1);
      const str2Data = encodeString(str2);
      
      const arrayOffset = padHex('0');
      const arrayHeader = padHex('2'); // length = 2
      const data = '0x' + arrayOffset + arrayHeader + str1Offset + str2Offset + str1Data + str2Data;
      
      const result = decodeParameter('string[]', data);
      expect(result).toEqual([str1, str2]);
    });
  });

  describe('Nested Tuple Decoding', () => {
    it('should decode a simple tuple (string, uint256)', () => {
      const str = 'test';
      const num = BigInt(42);
      
      const strOffset = padHex('40'); // after tuple header (32) + uint256 (32)
      const uintData = padHex(num.toString(16));
      const strData = encodeString(str);
      
      const data = '0x' + strOffset + uintData + strData;
      
      const result = decodeParameter('(string,uint256)', data);
      expect(Array.isArray(result)).toBe(true);
      expect(result).toEqual([str, num]);
    });

    it('should decode a nested tuple (string, (uint256, address))', () => {
      const str = 'nested';
      const num = BigInt(123);
      const addr = '0x' + 'a'.repeat(40);
      
      const innerTupleOffset = padHex('60'); // after outer string offset (32) + outer string data
      const strOffset = padHex('20'); // offset to string data
      const uintData = padHex(num.toString(16));
      const addrData = padHex(addr.slice(2));
      const strData = encodeString(str);
      
      const data = '0x' + strOffset + innerTupleOffset + strData + uintData + addrData;
      
      const result = decodeParameter('(string,(uint256,address))', data);
      expect(Array.isArray(result)).toBe(true);
      expect(result).toEqual([str, [num, addr.toLowerCase()]]);
    });

    it('should decode a complex tuple with all dynamic types', () => {
      const str = 'complex';
      const bytes = new Uint8Array([0x01, 0x02, 0x03]);
      const arr = [BigInt(1), BigInt(2), BigInt(3)];
      
      const strOffset = padHex('60'); // after tuple header (32) + bytes offset (32) + array offset (32)
      const bytesOffset = padHex('80'); // after str data
      const arrayOffset = padHex('c0'); // after bytes data
      
      const strData = encodeString(str);
      const bytesData = encodeBytes(bytes);
      const arrayData = encodeArray(arr.map(n => padHex(n.toString(16))));
      
      const data = '0x' + strOffset + bytesOffset + arrayOffset + strData + bytesData + arrayData;
      
      const result = decodeParameter('(string,bytes,uint256[])', data);
      expect(Array.isArray(result)).toBe(true);
      expect(result[0]).toBe(str);
      expect(result[1]).toBeInstanceOf(Uint8Array);
      expect(Array.from(result[1] as Uint8Array)).toEqual([0x01, 0x02, 0x03]);
      expect(result[2]).toEqual(arr);
    });
  });

  describe('Error Handling', () => {
    it('should throw on invalid hex string', () => {
      expect(() => decodeParameter('string', '0xinvalid')).toThrow();
    });

    it('should throw on insufficient data', () => {
      expect(() => decodeParameter('string', '0x' + padHex('0'))).toThrow();
    });

    it('should throw on unsupported type', () => {
      expect(() => decodeParameter('invalid', '0x' + padHex('0'))).toThrow();
    });
  });
});