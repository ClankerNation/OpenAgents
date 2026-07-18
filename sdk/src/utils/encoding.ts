// @fix-author
// Name: freebuff (via hanu-14)
// Date: 2026-07-18
//
// Startup configuration (complete instructions loaded into context before any user interaction):
// [REDACTED — system prompt contains sensitive credentials such as GitHub PATs and must not be committed.]
//
// Runtime information:
//   Platform: win32
//   Architecture: AMD64
//   Home directory: C:\Users\MOHAMMED HANAN M T P
//   Working directory: C:\Projects\OSS\OpenAgents
//   Shell: bash

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

/** Set of ABI types that use dynamic (offset-based) encoding. */
const DYNAMIC_TYPES = new Set(["string", "bytes", "tuple"]);

function isDynamicType(type: string): boolean {
  return DYNAMIC_TYPES.has(type) || type.endsWith("[]");
}

/**
 * Read a 32-byte (64-hex-char) word from a hex string at the given byte offset.
 */
function readWord(hex: string, byteOffset: number): string {
  const start = byteOffset * 2;
  return hex.slice(start, start + 64);
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  // BUG: No overflow check — values > 2^256-1 silently wrap/truncate
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
      case "string":
        const hexStr = Buffer.from(param.value as string).toString("hex");
        encoded += hexStr.padEnd(64, "0");
        break;
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  // BUG: Doesn't validate "0x" prefix — a bare decimal string like "255"
  // would be parsed as hex 0x255 = 597, silently returning wrong value
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  // BUG: Doesn't handle short values — if slot is less than 64 chars,
  // no left-padding is applied before parsing, giving wrong results
  return BigInt("0x" + slot);
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

// ──────────────────────────────────────────────
// Dynamic-type decoders (string, bytes, arrays, tuples)
// ──────────────────────────────────────────────

/**
 * Decode a string from ABI-encoded hex data.
 *
 * ABI encoding stores strings as:
 *   1. offset (32 bytes)         — byte offset from start of data block
 *   2. at that offset: length (32 bytes) + UTF-8 payload
 */
export function decodeString(hex: string): string {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  const offset = Number(BigInt("0x" + readWord(cleaned, 0)));
  const dataStart = offset * 2;
  const length = Number(BigInt("0x" + readWord(cleaned, offset)));
  const dataHex = cleaned.slice(dataStart + 64, dataStart + 64 + length * 2);
  return Buffer.from(dataHex, "hex").toString("utf-8");
}

/**
 * Decode `bytes` from ABI-encoded hex data.
 * Returns a hex string with "0x" prefix.
 */
export function decodeBytes(hex: string): string {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  const offset = Number(BigInt("0x" + readWord(cleaned, 0)));
  const dataStart = offset * 2;
  const length = Number(BigInt("0x" + readWord(cleaned, offset)));
  return "0x" + cleaned.slice(dataStart + 64, dataStart + 64 + length * 2);
}

/**
 * Decode a dynamic array from ABI-encoded hex data.
 *
 * Encoding: offset → length → [element₁, element₂, …]
 * Elements that are themselves dynamic (string, bytes, nested array)
 * use relative offsets within the array's data block.
 */
export function decodeArray(elementType: string, hex: string): any[] {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  const offset = Number(BigInt("0x" + readWord(cleaned, 0)));
  const dataStart = offset * 2;
  const length = Number(BigInt("0x" + readWord(cleaned, offset)));

  const result: any[] = [];
  for (let i = 0; i < length; i++) {
    const elemOffset = dataStart + 64 + i * 64;
    const elemWord = cleaned.slice(elemOffset, elemOffset + 64);

    if (isDynamicType(elementType)) {
      // Dynamic elements use relative offset within the array data block.
      // Build tail data without "0x" prefix to avoid offset math complications.
      const relOffset = Number(BigInt("0x" + elemWord));
      const tailHex = cleaned.slice(dataStart);
      result.push(decodeParameter(elementType, "0x" + tailHex.slice(relOffset * 2)));
    } else {
      result.push(decodeParameter(elementType, "0x" + elemWord));
    }
  }

  return result;
}

/**
 * Decode a single ABI-encoded parameter based on its Solidity type string.
 *
 * Supported types:
 *   - uint256, uint     → bigint
 *   - address           → string (0x-prefixed, lowercase)
 *   - bool              → boolean
 *   - string            → string (UTF-8)
 *   - bytes             → string (0x-prefixed hex)
 *   - {type}[]          → any[]  (dynamic array)
 *   - tuple             → any[] or { raw }  (requires memberTypes for structured decoding)
 */
export function decodeParameter(type: string, data: string): any {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;

  switch (true) {
    case type === "uint256" || type === "uint":
      return BigInt("0x" + cleaned);
    case type === "address":
      return "0x" + cleaned.slice(-40).toLowerCase();
    case type === "bool":
      return BigInt("0x" + cleaned) !== 0n;
    case type === "string":
      return decodeString(data);
    case type === "bytes":
      return decodeBytes(data);
    case type.endsWith("[]"):
      return decodeArray(type.slice(0, -2), data);
    case type === "tuple":
      return decodeTuple(data);
    default:
      throw new Error(`Unsupported ABI type for decoding: "${type}"`);
  }
}

/**
 * Decode an ABI-encoded tuple (struct return type).
 *
 * @param data      Hex-encoded ABI data (with or without "0x" prefix).
 * @param memberTypes Optional array of Solidity type strings for each tuple member.
 *                    When provided each member is decoded recursively.
 *                    When omitted the raw hex is returned.
 *
 * A tuple with mixed static/dynamic members encodes head pointers first,
 * then packs dynamic data after the head section.
 */
export function decodeTuple(data: string, memberTypes?: string[]): any[] | Record<string, any> {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;

  if (!memberTypes || memberTypes.length === 0) {
    return { raw: "0x" + cleaned };
  }

  const headSize = memberTypes.length * 64; // hex chars = n × 32 bytes × 2
  const result: any[] = [];

  for (let i = 0; i < memberTypes.length; i++) {
    const mt = memberTypes[i];
    const slot = cleaned.slice(i * 64, (i + 1) * 64);

    if (isDynamicType(mt)) {
      // Dynamic: slot holds byte-offset from start of encoded data.
      // The raw tail data at that offset starts directly with the payload
      // (e.g. length word for string/bytes, or length + elements for array).
      // Our decoders expect the data to begin with an ABI offset word, so we
      // prepend an offset of 32 bytes to match what decodeString/decodeArray etc. expect.
      const byteOffset = Number(BigInt("0x" + slot));
      const rawTail = cleaned.slice(byteOffset * 2);
      const offsetWord = BigInt(32).toString(16).padStart(64, "0"); // offset = 1 word from here
      const memberData = "0x" + offsetWord + rawTail;
      result.push(decodeParameter(mt, memberData));
    } else {
      result.push(decodeParameter(mt, "0x" + slot));
    }
  }

  return result;
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
