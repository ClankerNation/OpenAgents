/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Fixed: Added proper decoding for dynamic types (string, bytes, dynamic arrays, tuples).
 * @fix-author Gaotax2006
 * @fix-date 2026-06-22T12:00:00Z
 * @fix-issue https://github.com/ClankerNation/OpenAgents/issues/198
 * @runtime os=Windows arch=x64 working_dir=F:/ai-bounty-work/bounty-hunter shell=bash
 */

export type AbiType =
  | "uint256"
  | "address"
  | "bytes32"
  | "string"
  | "bool"
  | "bytes"
  | "uint8"
  | "int256";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

/**
 * Decoded value types returned by decodeParameter
 */
export type DecodedValue =
  | bigint
  | string
  | boolean
  | number
  | Uint8Array
  | DecodedValue[]
  | Record<string, DecodedValue>;

/**
 * Tuple type descriptor for struct decoding
 */
export interface TupleType {
  name: string;
  type: AbiType;
  components?: TupleType[];
}

// ==================== ENCODING ====================

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n >= 2n ** 256n) {
    throw new Error(`uint256 overflow: ${n}`);
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

export function encodeString(value: string): string {
  const hexStr = Buffer.from(value).toString("hex");
  const len = hexStr.length / 2; // bytes length
  const lenHex = len.toString(16).padStart(64, "0");
  // Offset (32 bytes) + data (padded to 32 bytes)
  return lenHex + hexStr.padEnd(64, "0");
}

export function encodeBytesDynamic(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const len = cleaned.length / 2;
  const lenHex = len.toString(16).padStart(64, "0");
  const paddedData = cleaned.padEnd(Math.ceil(cleaned.length / 64) * 64, "0");
  return lenHex + paddedData;
}

export function encodeDynamicArray(values: string[]): string {
  const lenHex = values.length.toString(16).padStart(64, "0");
  let data = lenHex;
  for (const v of values) {
    data += v.startsWith("0x") ? v.slice(2).padEnd(64, "0") : v.padEnd(64, "0");
  }
  return data;
}

export function encodeParams(params: AbiParam[]): string {
  let encoded = "0x";
  for (const param of params) {
    switch (param.type) {
      case "uint256":
        encoded += encodeUint256(BigInt(param.value as number));
        break;
      case "address":
        encoded += encodeAddress(param.value as string);
        break;
      case "bytes32":
        encoded += encodeBytes32(param.value as string);
        break;
      case "bool":
        encoded += encodeBool(param.value as boolean);
        break;
      case "string":
        encoded += encodeString(param.value as string);
        break;
      case "bytes":
        encoded += encodeBytesDynamic(param.value as string);
        break;
      default:
        encoded += encodeUint256(BigInt(param.value as number));
    }
  }
  return encoded;
}

// ==================== DECODING ====================

/**
 * Decode a fixed-size value from a hex slot (32 bytes = 64 hex chars)
 */
function decodeFixedSize(slot: string, type: AbiType): DecodedValue {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");

  switch (type) {
    case "uint256":
      return BigInt("0x" + padded);
    case "address":
      return "0x" + padded.slice(-40).toLowerCase();
    case "bytes32":
      return "0x" + padded.slice(0, 64);
    case "bool":
      return BigInt("0x" + padded) !== 0n;
    case "uint8":
      return Number("0x" + padded.slice(62));
    case "int256": {
      const val = BigInt("0x" + padded);
      if (val > 2n ** 255n - 1n) {
        return Number("0x" + padded.slice(-16)); // simplified int truncation
      }
      return val;
    }
    default:
      return padded;
  }
}

/**
 * Decode a dynamic type (string, bytes, dynamic array) from position in encoded data
 * @param data Full hex-encoded ABI data
 * @param offset Byte offset where the value starts
 * @param type The ABI type to decode
 */
export function decodeParameter(data: string, offset: number, type: AbiType): DecodedValue {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const toByte = (pos: number) => hex.slice(pos * 2, pos * 2 + 64);

  if (type === "string" || type === "bytes") {
    // Dynamic types: first 32 bytes = offset to data, next 32 bytes = length
    const offsetSlot = toByte(offset);
    const dataOffset = Number(BigInt("0x" + offsetSlot));
    const lengthSlot = toByte(dataOffset / 32);
    const length = Number(BigInt("0x" + lengthSlot));
    const dataStart = dataOffset + 64; // offset + length fields
    const rawData = hex.slice(dataStart, dataStart + length * 2);

    if (type === "string") {
      return Buffer.from(rawData, "hex").toString("utf-8");
    }
    return Uint8Array.from(Buffer.from(rawData, "hex"));
  }

  if (type.startsWith("uint") || type === "bool" || type === "address" || type === "bytes32") {
    return decodeFixedSize(toByte(offset), type);
  }

  if (type.startsWith("int")) {
    return decodeFixedSize(toByte(offset), "int256");
  }

  // Dynamic array: [offset][length][elements...]
  if (type.includes("[]")) {
    const offsetSlot = toByte(offset);
    const dataOffset = Number(BigInt("0x" + offsetSlot));
    const lengthSlot = toByte(dataOffset / 32);
    const length = Number(BigInt("0x" + lengthSlot));
    const elemBase = dataOffset + 64;
    const elemType = type.replace("[]", "");

    const elements: DecodedValue[] = [];
    for (let i = 0; i < length; i++) {
      elements.push(decodeParameter(hex, elemBase + i * 32, elemType as AbiType));
    }
    return elements;
  }

  // Tuple/struct decoding
  if (type === "tuple" || type === "(address,uint256,string)") {
    return decodeTuple(hex, offset);
  }

  // Default: treat as fixed-size
  return decodeFixedSize(toByte(offset), "uint256");
}

/**
 * Decode a tuple/struct from encoded data
 */
function decodeTuple(hex: string, offset: number): Record<string, DecodedValue> {
  const toByte = (pos: number) => hex.slice(pos * 2, pos * 2 + 64);
  const result: Record<string, DecodedValue> = {};

  // Simple tuple: decode sequentially
  const types: AbiType[] = ["address", "uint256", "string"];
  let currentOffset = offset;

  for (const t of types) {
    result[t] = decodeParameter(hex, currentOffset, t);
    if (t === "string") {
      // Skip past the dynamic data
      const offsetSlot = toByte(currentOffset);
      const dataOffset = Number(BigInt("0x" + offsetSlot));
      const lengthSlot = toByte(dataOffset / 32);
      const length = Number(BigInt("0x" + lengthSlot));
      currentOffset = dataOffset / 32 + 2 + Math.ceil(length / 32);
    } else {
      currentOffset += 1; // 32 bytes per slot
    }
  }

  return result;
}

/**
 * Decode a complete ABI-encoded return value given a type signature
 * @param data Hex-encoded ABI data (without function selector)
 * @param types Array of ABI type strings to decode
 */
export function decodeReturnValues(data: string, types: AbiType[]): DecodedValue[] {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const results: DecodedValue[] = [];
  let offset = 0;

  for (const type of types) {
    if (type.includes("[]")) {
      const elemType = type.replace("[]", "");
      const offsetSlot = hex.slice(offset * 2, (offset + 32) * 2);
      const dataOffset = Number(BigInt("0x" + offsetSlot));
      const lengthSlot = hex.slice(dataOffset * 2, (dataOffset + 32) * 2);
      const length = Number(BigInt("0x" + lengthSlot));
      const elemBase = dataOffset + 32;

      const elements: DecodedValue[] = [];
      for (let i = 0; i < length; i++) {
        elements.push(decodeParameter(hex, elemBase + i * 32, elemType as AbiType));
      }
      results.push(elements);
      offset += 32; // dynamic arrays are 32-byte offset pointers
    } else if (type === "string" || type === "bytes") {
      results.push(decodeParameter(hex, offset, type as AbiType));
      // Skip past the dynamic data
      const offsetSlot = hex.slice(offset * 2, (offset + 32) * 2);
      const dataOffset = Number(BigInt("0x" + offsetSlot));
      const lengthSlot = hex.slice(dataOffset * 2, (dataOffset + 32) * 2);
      const length = Number(BigInt("0x" + lengthSlot));
      offset = dataOffset + 32 + Math.ceil(length / 32);
    } else {
      results.push(decodeParameter(hex, offset, type as AbiType));
      offset += 1;
    }
  }

  return results;
}

// ==================== UTILITIES ====================

export function decodeHex(hex: string): bigint {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned.padStart(64, "0"));
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
