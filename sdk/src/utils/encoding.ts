/**
 * @fix-author rafaio1
 * @date 2026-08-25T05:00:00Z
 * @runtime linux x64 /tmp/openagents_issue_198 bash
 * @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for dynamic ABI decoding (Issue #198)
 */

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Supports fixed-size types (uint256, address, bool, bytes32) and dynamic
 * types (string, bytes, arrays, tuples) per Ethereum ABI specification.
 *
 * Closes #198
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
  value: string | number | bigint | boolean | Uint8Array | AbiParam[];
  /** For tuple types: ordered list of component types */
  components?: AbiParam[];
}

const MAX_UINT256 = BigInt("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");

// ─── Encoding ────────────────────────────────────────────────────────────────

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new RangeError(`uint256 overflow: ${n}`);
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  if (!/^[a-fA-F0-9]{40}$/.test(cleaned)) {
    throw new Error(`Invalid address: ${address}`);
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length > 64) {
    throw new Error("bytes32 exceeds 32 bytes");
  }
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

/**
 * Encode a dynamic string as offset-prefixed ABI data.
 * Returns the tail segment (offset word + length + padded data).
 */
function encodeStringTail(value: string): string {
  const hex = Buffer.from(value, "utf-8").toString("hex");
  const len = Math.ceil(hex.length / 2);
  const paddedData = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return encodeUint256(len) + paddedData;
}

/**
 * Encode dynamic bytes as offset-prefixed ABI data.
 */
function encodeBytesTail(value: Uint8Array | string): string {
  const hex =
    typeof value === "string"
      ? value.startsWith("0x")
        ? value.slice(2)
        : value
      : Buffer.from(value).toString("hex");
  const len = Math.ceil(hex.length / 2);
  const paddedData = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return encodeUint256(len) + paddedData;
}

export function encodeParams(params: AbiParam[]): string {
  // Separate head (static slots / offsets) from tails (dynamic data)
  let head = "";
  let tails = "";
  let dynamicOffset = params.length * 32; // each param occupies one 32-byte slot in head

  // First pass: compute tail lengths to build correct offsets
  const tailSegments: string[] = [];
  for (const param of params) {
    if (isDynamic(param.type)) {
      const seg = getDynamicTail(param);
      tailSegments.push(seg);
    } else {
      tailSegments.push("");
    }
  }

  // Compute cumulative tail offsets
  let runningTailLen = 0;
  const offsets: number[] = [];
  for (let i = 0; i < params.length; i++) {
    if (isDynamic(params[i].type)) {
      offsets.push(dynamicOffset + runningTailLen);
      runningTailLen += (tailSegments[i].length / 2); // hex chars → bytes
    } else {
      offsets.push(0);
    }
  }

  // Build head + tails
  for (let i = 0; i < params.length; i++) {
    const param = params[i];
    if (isDynamic(param.type)) {
      head += encodeUint256(offsets[i]);
      tails += tailSegments[i];
    } else {
      head += encodeStaticParam(param);
    }
  }

  return "0x" + head + tails;
}

function isDynamic(type: AbiType): boolean {
  return type === "string" || type === "bytes" || type === "tuple";
}

function getDynamicTail(param: AbiParam): string {
  switch (param.type) {
    case "string":
      return encodeStringTail(param.value as string);
    case "bytes":
      return encodeBytesTail(param.value as Uint8Array | string);
    case "tuple":
      // Encode tuple components recursively as a dynamic struct
      return encodeTupleTail(param.components || []);
    default:
      return "";
  }
}

function encodeTupleTail(components: AbiParam[]): string {
  // Re-use encodeParams logic but without the 0x prefix
  const encoded = encodeParams(components);
  return encoded.slice(2);
}

function encodeStaticParam(param: AbiParam): string {
  switch (param.type) {
    case "uint256":
      return encodeUint256(BigInt(param.value as number | bigint));
    case "address":
      return encodeAddress(param.value as string);
    case "bytes32":
      return encodeBytes32(param.value as string);
    case "bool":
      return encodeBool(param.value as boolean);
    default:
      throw new Error(`Unsupported static type: ${param.type}`);
  }
}

// ─── Decoding ────────────────────────────────────────────────────────────────

export function decodeHex(hex: string): bigint {
  if (!hex) throw new Error("Empty hex string");
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[a-fA-F0-9]+$/.test(cleaned)) {
    throw new Error(`Invalid hex: ${hex}`);
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const padded = slot.padStart(64, "0");
  return decodeHex(padded);
}

export function decodeAddress(slot: string): string {
  const raw = slot.padStart(64, "0").slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return decodeHex(slot.padStart(64, "0")) !== 0n;
}

/**
 * Decode a dynamic string from ABI-encoded calldata at the given byte offset.
 * Reads: [length (32 bytes)] [UTF-8 data (padded to 32 bytes)]
 */
export function decodeString(data: string, offsetBytes: number): string {
  const hex = stripPrefix(data);
  const offsetChars = offsetBytes * 2;

  // Read length
  const lengthSlot = hex.slice(offsetChars, offsetChars + 64);
  const length = Number(decodeHex(lengthSlot));

  // Read UTF-8 bytes
  const dataStart = offsetChars + 64;
  const dataHex = hex.slice(dataStart, dataStart + length * 2);
  return Buffer.from(dataHex, "hex").toString("utf-8");
}

/**
 * Decode dynamic bytes from ABI-encoded calldata at the given byte offset.
 * Returns a Uint8Array.
 */
export function decodeBytes(data: string, offsetBytes: number): Uint8Array {
  const hex = stripPrefix(data);
  const offsetChars = offsetBytes * 2;

  const lengthSlot = hex.slice(offsetChars, offsetChars + 64);
  const length = Number(decodeHex(lengthSlot));

  const dataStart = offsetChars + 64;
  const dataHex = hex.slice(dataStart, dataStart + length * 2);
  return Uint8Array.from(Buffer.from(dataHex, "hex"));
}

/**
 * Decode a dynamic array of homogeneous elements.
 * Each element is decoded according to elementType.
 */
export function decodeArray(
  data: string,
  offsetBytes: number,
  elementType: AbiType,
): unknown[] {
  const hex = stripPrefix(data);
  const offsetChars = offsetBytes * 2;

  const lengthSlot = hex.slice(offsetChars, offsetChars + 64);
  const length = Number(decodeHex(lengthSlot));

  const result: unknown[] = [];
  const elemSize = isDynamic(elementType) ? 32 : 32; // all elements occupy 32-byte slots (or offset pointers)

  for (let i = 0; i < length; i++) {
    const elemOffset = offsetChars + 64 + i * 64;
    if (isDynamic(elementType)) {
      // Element slot contains an offset relative to the start of the array data section
      const innerOffset = Number(decodeHex(hex.slice(elemOffset, elemOffset + 64)));
      // Inner offset is relative to the beginning of the array content (after length word)
      const absoluteOffset = offsetBytes + 32 + innerOffset;
      result.push(decodeDynamicElement(data, absoluteOffset, elementType));
    } else {
      result.push(decodeStaticElement(hex.slice(elemOffset, elemOffset + 64), elementType));
    }
  }

  return result;
}

/**
 * Decode a tuple (struct) from ABI-encoded data at the given byte offset.
 * Components are decoded sequentially following ABI struct layout rules.
 */
export function decodeTuple(
  data: string,
  offsetBytes: number,
  components: { type: AbiType; name?: string }[],
): Record<string, unknown> {
  const hex = stripPrefix(data);
  const baseChars = offsetBytes * 2;
  const result: Record<string, unknown> = {};

  for (let i = 0; i < components.length; i++) {
    const comp = components[i];
    const slotStart = baseChars + i * 64;
    const slot = hex.slice(slotStart, slotStart + 64);

    if (isDynamic(comp.type)) {
      const innerOffset = Number(decodeHex(slot));
      const absoluteOffset = offsetBytes + innerOffset;
      result[comp.name || `_${i}`] = decodeDynamicElement(data, absoluteOffset, comp.type);
    } else {
      result[comp.name || `_${i}`] = decodeStaticElement(slot, comp.type);
    }
  }

  return result;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function decodeDynamicElement(
  data: string,
  offsetBytes: number,
  type: AbiType,
): unknown {
  switch (type) {
    case "string":
      return decodeString(data, offsetBytes);
    case "bytes":
      return decodeBytes(data, offsetBytes);
    default:
      throw new Error(`Unsupported dynamic decode type: ${type}`);
  }
}

function decodeStaticElement(slot: string, type: AbiType): unknown {
  switch (type) {
    case "uint256":
      return decodeUint256(slot);
    case "address":
      return decodeAddress(slot);
    case "bytes32":
      return "0x" + slot.padStart(64, "0");
    case "bool":
      return decodeBool(slot);
    default:
      throw new Error(`Unsupported static decode type: ${type}`);
  }
}

function stripPrefix(hex: string): string {
  return hex.startsWith("0x") ? hex.slice(2) : hex;
}

// ─── Utility exports ─────────────────────────────────────────────────────────

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
