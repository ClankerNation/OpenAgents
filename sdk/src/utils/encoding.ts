/**
 * @fix-author
 * @name DecodeParameter Enhancement
 * @date 2026-06-03
 * @description Extended decodeParameter to handle dynamic ABI types: string, bytes, dynamic arrays, and tuples.
 *   Added recursive decoding for nested dynamic types and struct returns.
 * @runtime
 *   os: linux
 *   arch: x64
 *   working_dir: /home/user/projects/sdk
 *   shell: /bin/bash
 * @session-payload
 *   You are an expert TypeScript developer working on an SDK for blockchain interactions.
 *   The SDK currently has a utility module at sdk/src/utils/encoding.ts that provides ABI encoding/decoding.
 *   The existing decodeParameter function only handles fixed-size types (uint256, address, bool).
 *   Dynamic types (string, bytes, arrays, tuples) are returned as raw hex strings.
 *   Your task is to extend decodeParameter to properly decode these dynamic types according to the Ethereum ABI specification.
 *   Requirements:
 *   - String decoding: read offset (32 bytes), then length (32 bytes), then UTF-8 data
 *   - Bytes decoding: read offset (32 bytes), then length (32 bytes), then raw data as Buffer/Uint8Array
 *   - Dynamic array decoding: read offset (32 bytes), then length (32 bytes), then decode each element recursively
 *   - Tuple decoding: decode each component recursively, supporting nested structs
 *   - Maintain backward compatibility with existing fixed-size types
 *   - Add comprehensive JSDoc documentation
 *   - Add @fix-author block at top of file with name, date, and full session payload
 *   - Add @runtime with os, arch, working_dir, shell
 *   Acceptance Criteria:
 *   - String values decoded to JS string
 *   - Bytes decoded to Buffer/Uint8Array
 *   - Arrays decoded to JS arrays with correct types
 *   - Nested tuples decoded recursively
 *   - Test: decode complex return type with string + array + uint
 *   Constraints:
 *   - Only modify the single file sdk/src/utils/encoding.ts
 *   - Use existing dependencies (Buffer/Uint8Array support assumed)
 *   - Follow existing code style and patterns
 *   - Ensure all existing functionality continues to work
 *   - Handle edge cases: empty strings, empty arrays, zero-length bytes
 *   - Use proper TypeScript types and avoid any
 *   - Implement proper error handling for malformed data
 *   - Use bigint for uint256 values to maintain precision
 *   - Use the existing helper functions if available (e.g., hexToBuffer, bufferToHex)
 *   - The function signature should remain compatible with existing callers
 *   - Export all new helper functions for testing
 */

import { Buffer } from 'buffer';

// ============================================================
// Type Definitions
// ============================================================

/** Supported ABI parameter types */
export type AbiType =
  | 'uint256'
  | 'address'
  | 'bool'
  | 'string'
  | 'bytes'
  | `bytes${number}`
  | `uint${number}`
  | `int${number}`
  | `array`
  | `tuple`;

/** Decoded value types */
export type DecodedValue =
  | string
  | bigint
  | boolean
  | Buffer
  | DecodedValue[]
  | Record<string, DecodedValue>;

/** ABI parameter definition */
export interface AbiParameter {
  name?: string;
  type: AbiType;
  components?: AbiParameter[];
  internalType?: string;
}

// ============================================================
// Helper Functions
// ============================================================

/**
 * Converts a hex string to a Buffer.
 * @param hex - Hex string (with or without 0x prefix)
 * @returns Buffer containing the decoded bytes
 */
export function hexToBuffer(hex: string): Buffer {
  const cleanHex = hex.startsWith('0x') ? hex.slice(2) : hex;
  if (cleanHex.length % 2 !== 0) {
    throw new Error(`Invalid hex string length: ${cleanHex.length}`);
  }
  return Buffer.from(cleanHex, 'hex');
}

/**
 * Converts a Buffer to a hex string with 0x prefix.
 * @param buffer - Buffer to convert
 * @returns Hex string with 0x prefix
 */
export function bufferToHex(buffer: Buffer): string {
  return '0x' + buffer.toString('hex');
}

/**
 * Pads a hex string to 32 bytes (64 hex characters) with leading zeros.
 * @param hex - Hex string to pad
 * @returns Padded hex string (without 0x prefix)
 */
export function padToBytes32(hex: string): string {
  const cleanHex = hex.startsWith('0x') ? hex.slice(2) : hex;
  return cleanHex.padStart(64, '0');
}

/**
 * Extracts a 32-byte word from a hex string at a given offset.
 * @param data - Hex string (without 0x prefix)
 * @param offset - Byte offset (not hex character offset)
 * @returns 32-byte hex string (without 0x prefix)
 */
export function extractWord(data: string, offset: number): string {
  const charOffset = offset * 2;
  if (charOffset + 64 > data.length) {
    throw new Error(
      `Data too short: need ${charOffset + 64} chars, have ${data.length}`
    );
  }
  return data.slice(charOffset, charOffset + 64);
}

/**
 * Converts a 32-byte hex word to a bigint.
 * @param word - 32-byte hex string (without 0x prefix)
 * @returns BigInt value
 */
export function wordToBigInt(word: string): bigint {
  return BigInt('0x' + word);
}

/**
 * Converts a 32-byte hex word to a number (safe for lengths/counts).
 * @param word - 32-byte hex string (without 0x prefix)
 * @returns Number value
 */
export function wordToNumber(word: string): number {
  return Number(wordToBigInt(word));
}

/**
 * Checks if a type is a fixed-size type.
 * @param type - ABI type string
 * @returns True if the type is fixed-size
 */
export function isFixedSizeType(type: string): boolean {
  const fixedSizeTypes = [
    'uint256',
    'address',
    'bool',
    'uint8',
    'uint16',
    'uint32',
    'uint64',
    'uint128',
    'int8',
    'int16',
    'int32',
    'int64',
    'int128',
    'int256',
    'bytes1',
    'bytes2',
    'bytes3',
    'bytes4',
    'bytes8',
    'bytes16',
    'bytes32',
  ];
  return fixedSizeTypes.includes(type);
}

/**
 * Checks if a type is a dynamic type.
 * @param type - ABI type string
 * @returns True if the type is dynamic
 */
export function isDynamicType(type: string): boolean {
  return (
    type === 'string' ||
    type === 'bytes' ||
    type.startsWith('array') ||
    type === 'tuple' ||
    /^bytes\d+$/.test(type) === false
  );
}

// ============================================================
// Core Decoding Functions
// ============================================================

/**
 * Decodes a uint256 value from a 32-byte word.
 * @param word - 32-byte hex string (without 0x prefix)
 * @returns BigInt value
 */
export function decodeUint256(word: string): bigint {
  return wordToBigInt(word);
}

/**
 * Decodes an address from a 32-byte word.
 * @param word - 32-byte hex string (without 0x prefix)
 * @returns Address string (0x-prefixed, 40 hex chars)
 */
export function decodeAddress(word: string): string {
  return '0x' + word.slice(24); // Last 20 bytes
}

/**
 * Decodes a bool from a 32-byte word.
 * @param word - 32-byte hex string (without 0x prefix)
 * @returns Boolean value
 */
export function decodeBool(word: string): boolean {
  return wordToBigInt(word) !== BigInt(0);
}

/**
 * Decodes a string from ABI-encoded data.
 * @param data - Full ABI-encoded hex string (without 0x prefix)
 * @param offset - Byte offset where the string data starts
 * @returns Decoded string and the next byte offset
 */
export function decodeString(
  data: string,
  offset: number
): { value: string; nextOffset: number } {
  // Read offset pointer (32 bytes)
  const pointerWord = extractWord(data, offset);
  const stringOffset = wordToNumber(pointerWord);

  // Read length at the pointed location
  const lengthWord = extractWord(data, stringOffset);
  const length = wordToNumber(lengthWord);

  // Read UTF-8 data
  const dataStart = (stringOffset + 32) * 2; // Convert to hex char offset
  const dataEnd = dataStart + length * 2;
  const hexData = data.slice(dataStart, dataEnd);

  // Decode UTF-8
  const buffer = Buffer.from(hexData, 'hex');
  const value = buffer.toString('utf-8');

  return {
    value,
    nextOffset: offset + 32,
  };
}

/**
 * Decodes bytes from ABI-encoded data.
 * @param data - Full ABI-encoded hex string (without 0x prefix)
 * @param offset - Byte offset where the bytes data starts
 * @returns Decoded Buffer and the next byte offset
 */
export function decodeBytes(
  data: string,
  offset: number
): { value: Buffer; nextOffset: number } {
  // Read offset pointer (32 bytes)
  const pointerWord = extractWord(data, offset);
  const bytesOffset = wordToNumber(pointerWord);

  // Read length at the pointed location
  const lengthWord = extractWord(data, bytesOffset);
  const length = wordToNumber(lengthWord);

  // Read raw data
  const dataStart = (bytesOffset + 32) * 2; // Convert to hex char offset
  const dataEnd = dataStart + length * 2;
  const hexData = data.slice(dataStart, dataEnd);

  const value = Buffer.from(hexData, 'hex');

  return {
    value,
    nextOffset: offset + 32,
  };
}

/**
 * Decodes a dynamic array from ABI-encoded data.
 * @param data - Full ABI-encoded hex string (without 0x prefix)
 * @param offset - Byte offset where the array data starts
 * @param elementType - ABI type of the array elements
 * @param components - Component definitions for tuple elements
 * @returns Decoded array and the next byte offset
 */
export function decodeArray(
  data: string,
  offset: number,
  elementType: AbiType,
  components?: AbiParameter[]
): { value: DecodedValue[]; nextOffset: number } {
  // Read offset pointer (32 bytes)
  const pointerWord = extractWord(data, offset);
  const arrayOffset = wordToNumber(pointerWord);

  // Read length at the pointed location
  const lengthWord = extractWord(data, arrayOffset);
  const length = wordToNumber(lengthWord);

  const elements: DecodedValue[] = [];
  let currentOffset = arrayOffset + 32; // Skip length word

  for (let i = 0; i < length; i++) {
    const result = decodeParameterInternal(
      data,
      currentOffset,
      elementType,
      components
    );
    elements.push(result.value);
    currentOffset = result.nextOffset;
  }

  return {
    value: elements,
    nextOffset: offset + 32,
  };
}

/**
 * Decodes a tuple from ABI-encoded data.
 * @param data - Full ABI-encoded hex string (without 0x prefix)
 * @param offset - Byte offset where the tuple data starts
 * @param components - Component definitions for the tuple
 * @returns Decoded tuple object and the next byte offset
 */
export function decodeTuple(
  data: string,
  offset: number,
  components: AbiParameter[]
): { value: Record<string, DecodedValue>; nextOffset: number } {
  const result: Record<string, DecodedValue> = {};
  let currentOffset = offset;

  // First pass: calculate offsets for dynamic types
  const dynamicOffsets: Map<number, number> = new Map();
  let dynamicIndex = 0;
  let staticSize = 0;

  for (const component of components) {
    if (isDynamicType(component.type)) {
      dynamicOffsets.set(dynamicIndex, staticSize);
      staticSize += 32; // Pointer takes 32 bytes
    } else {
      staticSize += 32;
    }
    dynamicIndex++;
  }

  // Second pass: decode each component
  let tupleDataOffset = offset;
  let dynamicDataOffset = offset + staticSize;
  dynamicIndex = 0;

  for (const component of components) {
    if (isDynamicType(component.type)) {
      // Read the pointer
      const pointerWord = extractWord(data, tupleDataOffset);
      const pointer = wordToNumber(pointerWord);
      const absoluteOffset = offset + pointer;

      const decoded = decodeParameterInternal(
        data,
        absoluteOffset,
        component.type as AbiType,
        component.components
      );
      result[component.name || `_${dynamicIndex}`] = decoded.value;
      tupleDataOffset += 32;
    } else {
      const decoded = decodeParameterInternal(
        data,
        tupleDataOffset,
        component.type as AbiType,
        component.components
      );
      result[component.name || `_${dynamicIndex}`] = decoded.value;
      tupleDataOffset += 32;
    }
    dynamicIndex++;
  }

  return {
    value: result,
    nextOffset: tupleDataOffset,
  };
}

/**
 * Internal decode function that handles all types recursively.
 * @param data - Full ABI-encoded hex string (without 0x prefix)
 * @param offset - Byte offset for the current parameter
 * @param type - ABI type of the parameter
 * @param components - Component definitions for tuple types
 * @returns Decoded value and the next byte offset
 */
function decodeParameterInternal(
  data: string,
  offset: number,
  type: AbiType,
  components?: AbiParameter[]
): { value: DecodedValue; nextOffset: number } {
  const word = extractWord(data, offset);

  switch (type) {
    case 'uint256':
    case 'uint':
    case 'uint8':
    case 'uint16':
    case 'uint32':
    case 'uint64':
    case 'uint128':
      return {
        value: decodeUint256(word),
        nextOffset: offset + 32,
      };

    case 'address':
      return {
        value: decodeAddress(word),
        nextOffset: offset + 32,
      };

    case 'bool':
      return {
        value: decodeBool(word),
        nextOffset: offset + 32,
      };

    case 'string':
      return decodeString(data, offset);

    case 'bytes':
      return decodeBytes(data, offset);

    case 'array':
      if (!components || components.length === 0) {
        throw new Error('Array type requires component definition');
      }
      return decodeArray(
        data,
        offset,
        components[0].type as AbiType,
        components[0].components
      );

    case 'tuple':
      if (!components) {
        throw new Error('Tuple type requires component definitions');
      }
      return decodeTuple(data, offset, components);

    default:
      // Handle bytes<N> types
      if (/^bytes\d+$/.test(type)) {
        const match = type.match(/^bytes(\d+)$/);
        if (match) {
          const byteLength = parseInt(match[1], 10);
          const hexLength = byteLength * 2;
          const hexData = word.slice(0, hexLength);
          return {
            value: Buffer.from(hexData, 'hex'),
            nextOffset: offset + 32,
          };
        }
      }

      // Handle int<N> types
      if (/^int\d+$/.test(type)) {
        return {
          value: decodeUint256(word),
          nextOffset: offset + 32,
        };
      }

      throw new Error(`Unsupported ABI type: ${type}`);
  }
}

/**
 * Main decode function for ABI-encoded parameters.
 * Handles both fixed-size and dynamic types.
 *
 * @param data - ABI-encoded hex string (with or without 0x prefix)
 * @param type - ABI type of the parameter
 * @param components - Component definitions for tuple types (optional)
 * @returns Decoded value
 *
 * @example
 * // Decode a uint256
 * decodeParameter('0x000000000000000000000000000000000000000000000000000000000000002a', 'uint256')
 * // => 42n
 *
 * @example
 * // Decode a string
 * decodeParameter('0x0000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000000d48656c6c6f2c20576f726c642100000000000000000000000000000000000000', 'string')
 * // => "Hello, World!"
 *
 * @example
 * // Decode a tuple with struct
 * const components = [
 *   { name: 'name', type: 'string' },
 *   { name: 'age', type: 'uint256' },
 *   { name: 'active', type: 'bool' }
 * ];
 * decodeParameter(encodedData, 'tuple', components)
 * // => { name: 'Alice', age: 30n, active: true }
 */
export function decodeParameter(
  data: string,
  type: AbiType,
  components?: AbiParameter[]
): DecodedValue {
  const cleanData = data.startsWith('0x') ? data.slice(2) : data;

  if (cleanData.length === 0) {
    throw new Error('Empty data provided for decoding');
  }

  const result = decodeParameterInternal(cleanData, 0, type, components);
  return result.value;
}

/**
 * Decodes multiple return values from a function call.
 * Handles complex return types including tuples with dynamic types.
 *
 * @param data - ABI-encoded return data hex string (with or without 0x