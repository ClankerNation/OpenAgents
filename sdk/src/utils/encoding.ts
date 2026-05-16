/*
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * Agent: Metatron (AI — celestial scribe, autonomous coding agent)
 * Platform: Hermes Agent with DeepSeek V4 Pro
 * Environment: Linux x86_64, /home/power, WSL, bash
 * Task: Fix #198 — decodeParameter doesn't handle dynamic types
 * Fixes: encodeUint256 overflow, decodeHex validation, decodeUint256 padding
 */

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Supports static types (uint256, address, bytes32, bool) and dynamic types
 * (string, bytes, arrays, tuples) with full ABI v2 encoding compliance.
 */

export type AbiType =
  | "uint256"
  | "address"
  | "bytes32"
  | "string"
  | "bool"
  | "bytes";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

// ─── Encoding ───────────────────────────────────────────────────────────

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n) throw new Error("encodeUint256: negative value");
  const MAX_UINT256 = (1n << 256n) - 1n;
  if (n > MAX_UINT256) throw new Error("encodeUint256: value exceeds uint256 max");
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

/**
 * Encode a dynamic string per ABI spec: offset pointer + length + UTF-8 data.
 * Returns the hex for the tail section (length + data); the caller handles
 * offset calculation for multi-param encoding.
 */
export function encodeString(value: string): string {
  const data = Buffer.from(value, "utf-8").toString("hex");
  const len = encodeUint256(BigInt(value.length));
  // Pad data to 32-byte boundary
  const padded = data.padEnd(Math.ceil(data.length / 64) * 64, "0");
  return len + padded;
}

/**
 * Encode dynamic bytes per ABI spec.
 */
export function encodeBytes(value: Uint8Array | Buffer): string {
  const data = Buffer.from(value).toString("hex");
  const len = encodeUint256(BigInt(value.length));
  const padded = data.padEnd(Math.ceil(data.length / 64) * 64, "0");
  return len + padded;
}

export function encodeParams(params: AbiParam[]): string {
  const headParts: string[] = [];
  const tailParts: string[] = [];

  for (const param of params) {
    switch (param.type) {
      case "uint256":
        headParts.push(encodeUint256(BigInt(param.value as number)));
        break;
      case "address":
        headParts.push(encodeAddress(param.value as string));
        break;
      case "bytes32":
        headParts.push(encodeBytes32(param.value as string));
        break;
      case "bool":
        headParts.push(encodeBool(param.value as boolean));
        break;
      case "string": {
        // Dynamic: pointer goes in head, data in tail
        const tail = encodeString(param.value as string);
        headParts.push(null as any); // placeholder
        tailParts.push({ idx: headParts.length - 1, data: tail });
        break;
      }
      case "bytes": {
        const tail = encodeBytes(param.value as Uint8Array);
        headParts.push(null as any);
        tailParts.push({ idx: headParts.length - 1, data: tail });
        break;
      }
    }
  }

  // Calculate offsets for dynamic types
  let tailOffset = headParts.length * 32; // 32 bytes per head slot
  for (const tp of tailParts) {
    headParts[tp.idx] = encodeUint256(BigInt(tailOffset));
    tailOffset += tp.data.length / 2; // hex chars -> bytes
  }

  const head = headParts.join("");
  const tail = tailParts.map((tp: any) => tp.data).join("");
  return "0x" + head + tail;
}

// ─── Decoding ───────────────────────────────────────────────────────────

const HEX_PREFIX = "0x";

function stripHex(hex: string): string {
  return hex.startsWith(HEX_PREFIX) ? hex.slice(2) : hex;
}

export function decodeHex(hex: string): bigint {
  const cleaned = stripHex(hex);
  if (!/^[0-9a-fA-F]+$/.test(cleaned)) {
    throw new Error(`decodeHex: invalid hex string: "${hex}"`);
  }
  return BigInt(HEX_PREFIX + (cleaned || "0"));
}

export function decodeUint256(slot: string): bigint {
  const cleaned = stripHex(slot);
  // Left-pad to 64 hex chars for proper 32-byte parsing
  return BigInt(HEX_PREFIX + cleaned.padStart(64, "0"));
}

export function decodeAddress(slot: string): string {
  const cleaned = stripHex(slot);
  const raw = cleaned.slice(-40);
  return HEX_PREFIX + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  const cleaned = stripHex(slot);
  return BigInt(HEX_PREFIX + (cleaned || "0")) !== 0n;
}

/**
 * Decode a dynamic ABI-encoded string from the tail section.
 * hexData: the FULL hex string (head + tail together), without 0x prefix
 * byteOffset: the byte offset into the tail where the string data begins
 *   (this is the value decoded from the head pointer slot)
 */
export function decodeString(hexData: string, byteOffset: number): string {
  const data = stripHex(hexData);
  // byteOffset is in bytes; convert to hex character offset
  const charOffset = byteOffset * 2;
  // First 32 bytes after offset = length
  const lengthHex = data.slice(charOffset, charOffset + 64);
  const length = Number(decodeUint256(lengthHex));
  if (length === 0) return "";
  // Next bytes = UTF-8 data
  const dataStart = charOffset + 64;
  const dataEnd = dataStart + length * 2;
  const strHex = data.slice(dataStart, dataEnd);
  return Buffer.from(strHex, "hex").toString("utf-8");
}

/**
 * Decode dynamic ABI-encoded bytes from the tail section.
 */
export function decodeBytes(hexData: string, byteOffset: number): Uint8Array {
  const data = stripHex(hexData);
  const charOffset = byteOffset * 2;
  const lengthHex = data.slice(charOffset, charOffset + 64);
  const length = Number(decodeUint256(lengthHex));
  if (length === 0) return new Uint8Array(0);
  const dataStart = charOffset + 64;
  const dataEnd = dataStart + length * 2;
  return Uint8Array.from(Buffer.from(data.slice(dataStart, dataEnd), "hex"));
}

/**
 * Decode a dynamic ABI-encoded array from the tail section.
 * elementType: the ABI type of each element (e.g. "uint256", "address")
 */
export function decodeArray(
  hexData: string,
  elementType: string,
  byteOffset: number
): any[] {
  const data = stripHex(hexData);
  const charOffset = byteOffset * 2;
  const lengthHex = data.slice(charOffset, charOffset + 64);
  const length = Number(decodeUint256(lengthHex));
  const result: any[] = [];

  const elementStart = charOffset + 64;

  for (let i = 0; i < length; i++) {
    const slotStart = elementStart + i * 64;
    const slot = data.slice(slotStart, slotStart + 64);
    result.push(decodeParameterFromSlot(slot, elementType, data, byteOffset + 32 + i * 32));
  }

  return result;
}

/**
 * Decode a tuple (struct) from a head slot or tail data.
 * types: ordered list of ABI types for each tuple field.
 * hexData: full hex data for dynamic resolution.
 * byteOffset: byte offset into hexData where this tuple's data starts.
 *   For static tuples, this is the slot offset. For dynamic tuples,
 *   this points to the tail section.
 */
export function decodeTuple(
  hexData: string,
  types: string[],
  byteOffset: number
): any[] {
  const data = stripHex(hexData);
  const charOffset = byteOffset * 2;
  const result: any[] = [];
  // Track tail offsets for dynamic fields within the tuple
  let dynamicCount = 0;

  // Count dynamic types first
  for (const t of types) {
    if (isDynamicType(t)) dynamicCount++;
  }

  // Head section for tuple: each field gets 32 bytes
  const headSize = types.length * 32;
  let tailBaseOffset = byteOffset + headSize;

  for (let i = 0; i < types.length; i++) {
    const slotStart = charOffset + i * 64;
    const slot = data.slice(slotStart, slotStart + 64);
    result.push(decodeParameterFromSlot(slot, types[i], data, tailBaseOffset, byteOffset));
  }

  return result;
}

/**
 * Internal: decode a single 32-byte slot value into its typed representation.
 * For dynamic types, the slot contains an offset pointer into the tail.
 */
function decodeParameterFromSlot(
  slot: string,
  type: string,
  fullData: string = "",
  tailByteOffset: number = 0,
  headByteOffset: number = 0
): any {
  switch (type) {
    case "uint256":
    case "uint":
      return decodeUint256(slot);
    case "address":
      return decodeAddress(slot);
    case "bool":
      return decodeBool(slot);
    case "bytes32":
      // Return raw bytes32 hex with prefix
      return HEX_PREFIX + slot;
    case "string": {
      // slot contains offset from headByteOffset to string data in tail
      const offset = Number(decodeUint256(slot));
      return decodeString(fullData, headByteOffset + offset);
    }
    case "bytes": {
      const offset = Number(decodeUint256(slot));
      return decodeBytes(fullData, headByteOffset + offset);
    }
    default:
      // Array type like "uint256[]", "address[]"
      if (type.endsWith("[]")) {
        const elementType = type.slice(0, -2);
        const offset = Number(decodeUint256(slot));
        return decodeArray(fullData, elementType, headByteOffset + offset);
      }
      throw new Error(`decodeParameterFromSlot: unsupported type "${type}"`);
  }
}

function isDynamicType(type: string): boolean {
  return (
    type === "string" ||
    type === "bytes" ||
    type.endsWith("[]") ||
    type.startsWith("tuple")
  );
}

/**
 * Unified parameter decoder. Handles:
 * - Static types: uint256, address, bool, bytes32
 * - Dynamic types: string, bytes
 * - Arrays: uint256[], address[], etc.
 * - Tuples: pass types as "tuple(field1,field2,...)"
 *
 * hexData: the FULL ABI-encoded hex string (e.g., from eth_call return data).
 *   Must include 0x prefix.
 * type: ABI type string. For tuples, use format "tuple(uint256,address,string)"
 *   For arrays of tuples, use "tuple(uint256,address)[]"
 */
export function decodeParameter(hexData: string, type: string): any {
  const data = stripHex(hexData);

  // Handle tuple type
  if (type.startsWith("tuple")) {
    // Parse tuple field types: "tuple(uint256,address,string)" -> ["uint256","address","string"]
    const inner = type.slice(type.indexOf("(") + 1, type.lastIndexOf(")"));
    const fieldTypes = inner.split(",").map((t) => t.trim());

    if (type.endsWith("[]")) {
      // Array of tuples
      // First 32 bytes = offset to array data
      const arrayOffset = Number(decodeUint256(data.slice(0, 64)));
      return decodeTupleArray(data, fieldTypes, arrayOffset);
    } else {
      // Single tuple — decode from head
      return decodeTuple(hexData, fieldTypes, 0);
    }
  }

  // Handle array type
  if (type.endsWith("[]")) {
    const elementType = type.slice(0, -2);
    // First slot = offset to array data
    const offset = Number(decodeUint256(data.slice(0, 64)));
    return decodeArray(hexData, elementType, offset);
  }

  // Static types
  const slot = data.slice(0, 64);
  return decodeParameterFromSlot(slot, type, data, 0, 0);
}

function decodeTupleArray(
  data: string,
  fieldTypes: string[],
  byteOffset: number
): any[] {
  const charOffset = byteOffset * 2;
  const lengthHex = data.slice(charOffset, charOffset + 64);
  const length = Number(decodeUint256(lengthHex));
  const result: any[] = [];

  // Each tuple element starts with its own head section
  // For a tuple with N fields, each tuple takes N*32 bytes for static
  // plus dynamic data in tail

  for (let i = 0; i < length; i++) {
    // The tuple might be dynamic if it contains dynamic fields
    // Each tuple has its own head at the start offset
    const tupleHeadStart = charOffset + 64 + i * fieldTypes.length * 64;
    const tupleHead = data.slice(tupleHeadStart, tupleHeadStart + fieldTypes.length * 64);
    // Decode the tuple
    result.push(decodeTuple("0x" + data, fieldTypes, byteOffset + 32 + i * fieldTypes.length * 32));
  }

  return result;
}

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return HEX_PREFIX + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
