/**
 * @fix-author
 *   name: Hermes Agent (autonomous)
 *   date: 2026-08-04
 *   pre-conversation:
 *     Host: Windows (10)
 *     User home directory: C:/Users/Maison
 *     Current working directory: C:/Users/Maison
 *     Note: on Windows, the machine hostname (e.g. from hostname or uname)
 *           is NOT the username.
 *     Shell: on this Windows host your terminal tool runs commands through
 *            bash (git-bash / MSYS), NOT PowerShell or cmd.exe.
 *     Python toolchain: python3=missing, python=3.11.15, uv=installed.
 *     Conversation started: Tuesday, August 04, 2026
 *     Model: deepseek-v4-pro
 *     Provider: deepseek
 *     Platform: subagent
 *   @runtime
 *     os: Windows 10
 *     arch: x64
 *     working_dir: C:/Users/Maison/Desktop/Bounty Hunter/openagents_fix_198
 *     shell: bash (git-bash / MSYS)
 */

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Supports ABI v2 head+tail encoding for dynamic types.
 */

import { createHash } from "crypto";

// Type Definitions

export type AbiType = "uint256" | "int256" | "address" | "bytes32" | "string" | "bytes" | "bool";

export interface AbiParam {
  type: AbiType | string;
  value: string | number | bigint | boolean | Uint8Array;
}

// Internal Helpers

/** Maximum value for uint256 (2^256 - 1) */
const UINT256_MAX = (1n << 256n) - 1n;

/**
 * Slice bytes from an offset with a given length.
 * Input is a hex string (without 0x prefix).
 */
function sliceBytes(data: string, offset: number, length: number): string {
  return data.slice(offset * 2, (offset + length) * 2);
}

/**
 * Read a 32-byte word from the data at the given byte offset.
 * Returns the hex string (64 chars) without 0x prefix.
 */
function readWord(data: string, byteOffset: number): string {
  const start = byteOffset * 2;
  const end = start + 64;
  if (end > data.length) {
    throw new Error(
      "readWord: byte offset " + byteOffset + " out of bounds (data length=" + (data.length / 2) + " bytes)"
    );
  }
  return data.slice(start, end);
}
/**
 * Check if an ABI type is dynamic (requires head+tail encoding).
 */
function isDynamicType(type: string): boolean {
  // Strip array brackets to check the base type
  const baseType = type.replace(/\[\d*\]?$/g, "");
  if (baseType === "string" || baseType === "bytes") {
    return true;
  }
  if (baseType.startsWith("tuple")) {
    // A tuple is dynamic if any of its members are dynamic
    const members = parseTupleMembers(baseType);
    return members.some((m) => isDynamicType(m));
  }
  // Arrays of dynamic types are dynamic
  if (type.endsWith("[]") || /\[\d+\]$/.test(type)) {
    return isDynamicType(type.replace(/\[\d*\]?$/, ""));
  }
  return false;
}

/**
 * Parse the member types from a tuple(...) type string,
 * correctly handling nested parentheses.
 */
function parseTupleMembers(tupleType: string): string[] {
  // Extract the content between the outer tuple(...) parentheses
  const match = tupleType.match(/^tuple\((.*)\)$/);
  if (!match) {
    throw new Error("parseTupleMembers: not a tuple type: " + tupleType);
  }
  const inner = match[1];
  const members: string[] = [];
  let depth = 0;
  let current = "";
  for (const ch of inner) {
    if (ch === "(" || ch === "[") {
      depth++;
      current += ch;
    } else if (ch === ")" || ch === "]") {
      depth--;
      current += ch;
    } else if (ch === "," && depth === 0) {
      members.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  if (current.trim()) {
    members.push(current.trim());
  }
  return members;
}

/**
 * Get the static size in bytes for a given type.
 */
function getStaticSize(type: string): number {
  if (type === "uint256" || type === "int256" || type === "address" || type === "bool" || type === "bytes32") {
    return 32;
  }
  if (type.startsWith("tuple")) {
    const members = parseTupleMembers(type);
    let size = 0;
    for (const m of members) {
      if (isDynamicType(m)) {
        size += 32;
      } else {
        size += getStaticSize(m);
      }
    }
    return size;
  }
  const fixedMatch = type.match(/^(.+)\[(\d+)\]$/);
  if (fixedMatch) {
    const elemType = fixedMatch[1];
    const count = parseInt(fixedMatch[2], 10);
    return getStaticSize(elemType) * count;
  }
  return 32;
}
/**
 * Recursively decode a single parameter from ABI-encoded data.
 * Handles: uint256, int256, address, bool, bytes32, string, bytes,
 *          type[] (dynamic arrays), tuple(...) (nested structs),
 *          tuple(...)[] (arrays of structs)
 */
function _decodeParam(
  data: string,
  type: string,
  offset: number
): [unknown, number] {
  // Static elementary types
  if (type === "uint256") {
    const word = readWord(data, offset);
    return [decodeUint256(word), offset + 32];
  }
  if (type === "int256") {
    const word = readWord(data, offset);
    return [decodeInt256(word), offset + 32];
  }
  if (type === "address") {
    const word = readWord(data, offset);
    return [decodeAddress(word), offset + 32];
  }
  if (type === "bool") {
    const word = readWord(data, offset);
    return [decodeBool(word), offset + 32];
  }
  if (type === "bytes32") {
    const word = readWord(data, offset);
    return ["0x" + word, offset + 32];
  }
  // Dynamic types: string, bytes
  if (type === "string") {
    const ptrWord = readWord(data, offset);
    const strOffset = Number(BigInt("0x" + ptrWord));
    return [decodeString(data, strOffset), offset + 32];
  }
  if (type === "bytes") {
    const ptrWord = readWord(data, offset);
    const bytesOffset = Number(BigInt("0x" + ptrWord));
    return [decodeBytes(data, bytesOffset), offset + 32];
  }
  // Dynamic array: type[]
  const arrayMatch = type.match(/^(.+)\[\]$/);
  if (arrayMatch) {
    const elementType = arrayMatch[1];
    const ptrWord = readWord(data, offset);
    const arrayOffset = Number(BigInt("0x" + ptrWord));
    const arr = decodeArray(data, arrayOffset, elementType);
    return [arr, offset + 32];
  }
  // Fixed-size array: type[N]
  const fixedArrayMatch = type.match(/^(.+)\[(\d+)\]$/);
  if (fixedArrayMatch) {
    const elementType = fixedArrayMatch[1];
    const length = parseInt(fixedArrayMatch[2], 10);
    return decodeFixedArray(data, offset, elementType, length);
  }
  // Tuple: tuple(...)
  if (type.startsWith("tuple")) {
    const dynamic = isDynamicType(type);
    if (dynamic) {
      const ptrWord = readWord(data, offset);
      const tupleOffset = Number(BigInt("0x" + ptrWord));
      const tuple = decodeTuple(data, tupleOffset, type);
      return [tuple, offset + 32];
    } else {
      const tuple = decodeTuple(data, offset, type);
      const staticSize = getStaticSize(type);
      return [tuple, offset + staticSize];
    }
  }
  throw new Error("_decodeParam: unsupported type: " + type);
}
/**
 * Decode a string from ABI-encoded data at the given tail offset.
 * String layout: [length (32 bytes)] [UTF-8 data (padded to 32-byte boundary)]
 */
function decodeString(data: string, offset: number): string {
  const lengthWord = readWord(data, offset);
  const length = Number(BigInt("0x" + lengthWord));
  const dataStart = offset + 32;
  const hexStr = sliceBytes(data, dataStart, length);
  const bytes = new Uint8Array(length);
  for (let i = 0; i < length; i++) {
    bytes[i] = parseInt(hexStr.slice(i * 2, i * 2 + 2), 16);
  }
  return new TextDecoder("utf-8").decode(bytes);
}

/**
 * Decode dynamic bytes from ABI-encoded data at the given tail offset.
 * Bytes layout: [length (32 bytes)] [raw data (padded to 32-byte boundary)]
 */
function decodeBytes(data: string, offset: number): Uint8Array {
  const lengthWord = readWord(data, offset);
  const length = Number(BigInt("0x" + lengthWord));
  const dataStart = offset + 32;
  const hexStr = sliceBytes(data, dataStart, length);
  const bytes = new Uint8Array(length);
  for (let i = 0; i < length; i++) {
    bytes[i] = parseInt(hexStr.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

/**
 * Decode a dynamic array from ABI-encoded data.
 * Array layout: [length (32 bytes)] [element 0] [element 1] ...
 */
function decodeArray(data: string, offset: number, elementType: string): unknown[] {
  const lengthWord = readWord(data, offset);
  const length = Number(BigInt("0x" + lengthWord));
  const result: unknown[] = [];
  if (isDynamicType(elementType)) {
    const headsStart = offset + 32;
    for (let i = 0; i < length; i++) {
      const ptrWord = readWord(data, headsStart + i * 32);
      const relOffset = Number(BigInt("0x" + ptrWord));
      const elemAbsOffset = headsStart + relOffset;
      const [val] = _decodeParam(data, elementType, elemAbsOffset);
      result.push(val);
    }
  } else if (elementType.startsWith("tuple")) {
    let currentOffset = offset + 32;
    for (let i = 0; i < length; i++) {
      const tupleData = decodeTuple(data, currentOffset, elementType);
      result.push(tupleData);
      currentOffset += getStaticSize(elementType);
    }
  } else {
    let currentOffset = offset + 32;
    for (let i = 0; i < length; i++) {
      const [val] = _decodeParam(data, elementType, currentOffset);
      result.push(val);
      currentOffset += 32;
    }
  }
  return result;
}

/**
 * Decode a fixed-size array from ABI-encoded data.
 */
function decodeFixedArray(
  data: string,
  offset: number,
  elementType: string,
  length: number
): [unknown[], number] {
  const result: unknown[] = [];
  let currentOffset = offset;
  for (let i = 0; i < length; i++) {
    const [val, newOffset] = _decodeParam(data, elementType, currentOffset);
    result.push(val);
    currentOffset = newOffset;
  }
  return [result, currentOffset];
}

/**
 * Decode a tuple from ABI-encoded data at the given byte offset.
 */
function decodeTuple(data: string, offset: number, tupleType: string): Record<string, unknown> {
  const members = parseTupleMembers(tupleType);
  const result: Record<string, unknown> = {};
  // Compute the head size for this tuple
  let headEnd = offset;
  for (const memberType of members) {
    if (isDynamicType(memberType)) {
      headEnd += 32;
    } else {
      headEnd += getStaticSize(memberType);
    }
  }
  let headPtr = offset;
  for (let i = 0; i < members.length; i++) {
    const memberType = members[i];
    if (isDynamicType(memberType)) {
      const ptrWord = readWord(data, headPtr);
      const relOffset = Number(BigInt("0x" + ptrWord));
      const [val] = _decodeParam(data, memberType, offset + relOffset);
      result["member" + i] = val;
      headPtr += 32;
    } else {
      const [val, newHead] = _decodeParam(data, memberType, headPtr);
      result["member" + i] = val;
      headPtr = newHead;
    }
  }
  return result;
}
// Encoding Functions

/** Encode a uint256 value as a 64-char hex string with overflow check. */
export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n) {
    throw new Error("encodeUint256: negative values are not allowed (got " + n + ")");
  }
  if (n > UINT256_MAX) {
    throw new Error(
      "encodeUint256: value exceeds uint256 max (2^256 - 1). Got " + n
    );
  }
  return n.toString(16).padStart(64, "0");
}

/** Encode an int256 value as a 64-char hex string (two's complement). */
export function encodeInt256(value: bigint | number): string {
  const n = BigInt(value);
  const INT256_MAX = (1n << 255n) - 1n;
  const INT256_MIN = -(1n << 255n);
  if (n < INT256_MIN || n > INT256_MAX) {
    throw new Error(
      "encodeInt256: value out of int256 range. Got " + n
    );
  }
  const mask = (1n << 256n) - 1n;
  const unsigned = n & mask;
  return unsigned.toString(16).padStart(64, "0");
}

/** Encode an Ethereum address as a 64-char hex string (left-zero-padded). */
export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  if (cleaned.length !== 40) {
    throw new Error(
      "encodeAddress: address must be 20 bytes (40 hex chars), got " + cleaned.length + " chars"
    );
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

/** Encode a bytes32 value as a 64-char hex string (right-zero-padded). */
export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length > 64) {
    throw new Error("encodeBytes32: data must be at most 32 bytes (64 hex chars)");
  }
  return cleaned.padEnd(64, "0");
}

/** Encode a bool as a 64-char hex string (0 or 1). */
export function encodeBool(value: boolean): string {
  return (value ? "1" : "0").padStart(64, "0");
}

/**
 * Encode a dynamic string into the ABI tail section.
 * Returns the head pointer hex and the tail data hex.
 */
export function encodeString(value: string): string;
export function encodeString(value: string, tailOffset: number): { head: string; tail: string };
export function encodeString(
  value: string,
  tailOffset?: number
): string | { head: string; tail: string } {
  const offset = tailOffset ?? 0;
  const encoded = Buffer.from(value, "utf-8").toString("hex");
  const length = encoded.length / 2;
  const head = offset.toString(16).padStart(64, "0");
  if (tailOffset === undefined) {
    // Simple mode: return just the encoded string
    return head + encoded.padEnd(Math.ceil(length / 32) * 32 * 2, "0");
  }
  let tail = length.toString(16).padStart(64, "0");
  tail += encoded.padEnd(Math.ceil(length / 32) * 32 * 2, "0");
  return { head, tail };
}

/**
 * Encode dynamic bytes (Uint8Array or hex string) into the ABI tail section.
 * Returns the head pointer hex and the tail data hex.
 */
export function encodeDynamicBytes(value: Uint8Array | string): string;
export function encodeDynamicBytes(value: Uint8Array | string, tailOffset: number): { head: string; tail: string };
export function encodeDynamicBytes(
  value: Uint8Array | string,
  tailOffset?: number
): string | { head: string; tail: string } {
  const offset = tailOffset ?? 0;
  let hexStr: string;
  if (typeof value === "string") {
    hexStr = value.startsWith("0x") ? value.slice(2) : value;
  } else {
    hexStr = Buffer.from(value).toString("hex");
  }
  const length = hexStr.length / 2;
  const head = offset.toString(16).padStart(64, "0");
  if (tailOffset === undefined) {
    // Simple mode: return just the encoded tail
    return head + hexStr.padEnd(Math.ceil(length / 32) * 32 * 2, "0");
  }
  let tail = length.toString(16).padStart(64, "0");
  tail += hexStr.padEnd(Math.ceil(length / 32) * 32 * 2, "0");
  return { head, tail };
}

/**
 * Encode an array of parameters using ABI v2 head+tail encoding.
 * Static types go inline in the head. Dynamic types (string, bytes) get
 * a pointer in the head and the data in the tail.
 */
export function encodeParams(params: AbiParam[]): string {
  const headSize = params.length * 32;
  const headParts: string[] = [];
  const tailParts: string[] = [];
  let currentTailOffset = headSize;
  for (const param of params) {
    const type = param.type;
    if (type === "uint256") {
      headParts.push(encodeUint256(BigInt(param.value as number | bigint)));
    } else if (type === "int256") {
      headParts.push(encodeInt256(BigInt(param.value as number | bigint)));
    } else if (type === "address") {
      headParts.push(encodeAddress(param.value as string));
    } else if (type === "bytes32") {
      headParts.push(encodeBytes32(param.value as string));
    } else if (type === "bool") {
      headParts.push(encodeBool(param.value as boolean));
    } else if (type === "string") {
      const { head, tail } = encodeString(param.value as string, currentTailOffset);
      headParts.push(head);
      tailParts.push(tail);
      currentTailOffset += tail.length / 2;
    } else if (type === "bytes") {
      const { head, tail } = encodeDynamicBytes(param.value as Uint8Array | string, currentTailOffset);
      headParts.push(head);
      tailParts.push(tail);
      currentTailOffset += tail.length / 2;
    } else {
      throw new Error("encodeParams: unsupported type: " + type);
    }
  }
  return "0x" + headParts.join("") + tailParts.join("");
}
// Decoding Functions

/**
 * Decode a hex string to a bigint, with validation of the 0x prefix.
 */
export function decodeHex(hex: string): bigint {
  if (typeof hex !== "string") {
    throw new Error("decodeHex: input must be a string");
  }
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (cleaned.length === 0) {
    return 0n;
  }
  if (!/^[0-9a-fA-F]+$/.test(cleaned)) {
    throw new Error("decodeHex: invalid hex characters");
  }
  return BigInt("0x" + cleaned);
}

/**
 * Decode a uint256 value from a 32-byte slot (64 hex chars).
 * Handles short values by left-padding to 64 chars.
 */
export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
}

/**
 * Decode an int256 value from a 32-byte slot (64 hex chars).
 * Handles two's complement negative values.
 */
export function decodeInt256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  const unsigned = BigInt("0x" + padded);
  const SIGN_BIT = 1n << 255n;
  const MASK = (1n << 256n) - 1n;
  if (unsigned & SIGN_BIT) {
    return unsigned - (MASK + 1n);
  }
  return unsigned;
}

/**
 * Decode an Ethereum address from a 32-byte slot.
 * Returns the 0x-prefixed, lowercase address.
 */
export function decodeAddress(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const raw = cleaned.slice(-40).padStart(40, "0");
  return "0x" + raw.toLowerCase();
}

/**
 * Decode a bool from a 32-byte slot.
 */
export function decodeBool(slot: string): boolean {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + (cleaned || "0")) !== 0n;
}

/**
 * Decode a single parameter from ABI-encoded data.
 *
 * Handles:
 *   - uint256, int256, address, bool, bytes32
 *   - string, bytes
 *   - type[] (dynamic arrays)
 *   - tuple(...) (nested structs)
 *   - tuple(...)[] (arrays of structs)
 */
export function decodeParameter(data: string, type: string): unknown {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const [value] = _decodeParam(cleaned, type, 0);
  return value;
}

/**
 * Batch-decode multiple parameters from ABI-encoded data.
 */
export function decodeParams(data: string, types: string[]): unknown[] {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const results: unknown[] = [];
  let offset = 0;
  for (const type of types) {
    const [value, newOffset] = _decodeParam(cleaned, type, offset);
    results.push(value);
    offset = newOffset;
  }
  return results;
}

// Function Selector and Calldata Packing

/**
 * Compute the Keccak-256 function selector (first 4 bytes) for a given signature.
 */
export function functionSelector(signature: string): string {
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

/**
 * Pack a function selector and encoded parameters into full calldata.
 */
export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
