// @fix-author rafaio1
// @date 2026-08-20
// @runtime ghostcli/codex linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType =
  | "uint256"
  | "address"
  | "bytes32"
  | "string"
  | "bool"
  | "bytes"
  | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | Buffer | Uint8Array | unknown[] | Record<string, unknown>;
  components?: AbiParam[]; // For tuple types
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > 2n ** 256n - 1n) {
    throw new Error("encodeUint256: overflow or underflow");
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
      case "string": {
        const hexStr = Buffer.from(param.value as string).toString("hex");
        encoded += hexStr.padEnd(64, "0");
        break;
      }
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  if (!hex.startsWith("0x")) {
    throw new Error("decodeHex: missing 0x prefix");
  }
  const cleaned = hex.slice(2);
  if (cleaned.length === 0) return 0n;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

/**
 * Decode a dynamic string from ABI-encoded hex data.
 * Format: offset (32 bytes) -> length (32 bytes) -> utf8 data (padded to 32 bytes)
 * @param data The full ABI-encoded hex string (without 0x prefix)
 * @param offset The byte offset where the string pointer lives (default 0)
 */
export function decodeString(data: string, offset: number = 0): string {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  // Read the offset pointer at the given position
  const pointerHex = cleanData.slice(offset * 2, offset * 2 + 64);
  const pointer = Number(BigInt("0x" + pointerHex));
  
  // At the pointer location, read length
  const lengthHex = cleanData.slice(pointer * 2, pointer * 2 + 64);
  const length = Number(BigInt("0x" + lengthHex));
  
  // Read the actual string bytes
  const strDataStart = pointer * 2 + 64;
  const strDataHex = cleanData.slice(strDataStart, strDataStart + length * 2);
  
  return Buffer.from(strDataHex, "hex").toString("utf8");
}

/**
 * Decode dynamic bytes from ABI-encoded hex data.
 * Format: offset (32 bytes) -> length (32 bytes) -> raw data (padded to 32 bytes)
 */
export function decodeBytes(data: string, offset: number = 0): Uint8Array {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  const pointerHex = cleanData.slice(offset * 2, offset * 2 + 64);
  const pointer = Number(BigInt("0x" + pointerHex));
  
  const lengthHex = cleanData.slice(pointer * 2, pointer * 2 + 64);
  const length = Number(BigInt("0x" + lengthHex));
  
  const bytesDataStart = pointer * 2 + 64;
  const bytesDataHex = cleanData.slice(bytesDataStart, bytesDataStart + length * 2);
  
  return Buffer.from(bytesDataHex, "hex");
}

/**
 * Decode a dynamic array of fixed-size elements from ABI-encoded hex data.
 * Format: offset -> length -> element[0] -> element[1] -> ...
 * @param elementType The ABI type of each array element (e.g., "uint256", "address")
 */
export function decodeArray(data: string, elementType: AbiType, offset: number = 0): unknown[] {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  const pointerHex = cleanData.slice(offset * 2, offset * 2 + 64);
  const pointer = Number(BigInt("0x" + pointerHex));
  
  const lengthHex = cleanData.slice(pointer * 2, pointer * 2 + 64);
  const length = Number(BigInt("0x" + lengthHex));
  
  const result: unknown[] = [];
  const elemSize = 32; // All fixed-size ABI elements are 32 bytes
  
  for (let i = 0; i < length; i++) {
    const elemOffset = pointer + 32 + i * elemSize;
    const elemHex = cleanData.slice(elemOffset * 2, elemOffset * 2 + 64);
    
    switch (elementType) {
      case "uint256":
        result.push(decodeUint256(elemHex));
        break;
      case "address":
        result.push(decodeAddress(elemHex));
        break;
      case "bool":
        result.push(decodeBool(elemHex));
        break;
      case "bytes32":
        result.push("0x" + elemHex);
        break;
      default:
        result.push("0x" + elemHex);
    }
  }
  
  return result;
}

/**
 * Decode a tuple (struct) from ABI-encoded hex data.
 * Recursively decodes each component according to its type.
 * @param components The ordered list of tuple field definitions
 */
export function decodeTuple(
  data: string,
  components: AbiParam[],
  offset: number = 0
): Record<string, unknown> {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  const result: Record<string, unknown> = {};
  
  let cursor = offset;
  
  for (const comp of components) {
    const slotHex = cleanData.slice(cursor * 2, cursor * 2 + 64);
    
    switch (comp.type) {
      case "uint256":
        result[comp.value as string || "field"] = decodeUint256(slotHex);
        cursor += 32;
        break;
      case "address":
        result[comp.value as string || "field"] = decodeAddress(slotHex);
        cursor += 32;
        break;
      case "bool":
        result[comp.value as string || "field"] = decodeBool(slotHex);
        cursor += 32;
        break;
      case "bytes32":
        result[comp.value as string || "field"] = "0x" + slotHex;
        cursor += 32;
        break;
      case "string":
        result[comp.value as string || "field"] = decodeString(cleanData, cursor);
        cursor += 32;
        break;
      case "bytes":
        result[comp.value as string || "field"] = decodeBytes(cleanData, cursor);
        cursor += 32;
        break;
      case "tuple":
        if (comp.components) {
          // Nested tuple: read inline if static, or follow pointer if dynamic
          // For simplicity, treat nested tuples as inline static decoding
          const nestedResult = decodeTuple(cleanData, comp.components, cursor);
          result[comp.value as string || "field"] = nestedResult;
          cursor += comp.components.length * 32;
        }
        break;
      default:
        result[comp.value as string || "field"] = "0x" + slotHex;
        cursor += 32;
    }
  }
  
  return result;
}

/**
 * High-level decodeParameter dispatcher.
 * Routes to the correct decoder based on the ABI type.
 */
export function decodeParameter(type: AbiType, data: string, components?: AbiParam[]): unknown {
  switch (type) {
    case "uint256":
      return decodeUint256(data);
    case "address":
      return decodeAddress(data);
    case "bool":
      return decodeBool(data);
    case "bytes32":
      return data.startsWith("0x") ? data : "0x" + data;
    case "string":
      return decodeString(data);
    case "bytes":
      return decodeBytes(data);
    case "tuple":
      if (!components) throw new Error("decodeParameter: tuple requires components");
      return decodeTuple(data, components);
    default:
      throw new Error(`decodeParameter: unsupported type ${type}`);
  }
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
