/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author kejuunuy
 * @fix-issue 198 — decodeParameter now handles dynamic ABI types
 *   (string, bytes, dynamic arrays, and nested dynamic arrays).
 */

export type AbiType =
  | "uint256"
  | "uint8"
  | "uint16"
  | "uint32"
  | "uint128"
  | "int256"
  | "int8"
  | "int16"
  | "int32"
  | "int128"
  | "address"
  | "bytes32"
  | "bytes"
  | "string"
  | "bool"
  | string; // allow compound types like "uint256[]", "address[3]", "bytes[]"

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
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

// ---------------------------------------------------------------------------
// Helpers for ABI type classification
// ---------------------------------------------------------------------------

/** Strip a leading `0x` prefix if present. */
function stripHexPrefix(hex: string): string {
  return hex.startsWith("0x") ? hex.slice(2) : hex;
}

/** Read a 32-byte word (64 hex chars) from `data` at the given byte offset. */
function readWord(data: string, byteOffset: number): string {
  const start = byteOffset * 2; // hex chars
  const word = data.slice(start, start + 64).padEnd(64, "0");
  return word;
}

/** Read a uint256 from a word. */
function readUint256FromHex(data: string, byteOffset: number): bigint {
  return BigInt("0x" + readWord(data, byteOffset));
}

/**
 * Returns `true` when `type` is an ABI *dynamic* type:
 *   - `bytes`, `string`
 *   - `T[]` (unbounded / dynamic-length array)
 *   - `T[N]` where T is itself dynamic
 */
function isDynamicType(type: string): boolean {
  if (type === "bytes" || type === "string") return true;

  // Array?  T[] or T[N]
  const arrayMatch = type.match(/^(.+?)(\[(\d*)?\])$/);
  if (arrayMatch) {
    const inner = arrayMatch[1];
    const size = arrayMatch[3];
    // Dynamic-length array T[] is always dynamic
    if (size === undefined || size === "") return true;
    // Fixed-length T[N] — dynamic if T is dynamic
    return isDynamicType(inner);
  }

  // tuple types — treated as dynamic if any component is dynamic
  // (not implemented in this PR, but the hook is here)
  return false;
}

/** Returns `{ base, size }` when `type` is a fixed-size static array `T[N]`. */
function isFixedArray(type: string): { base: string; size: number } | null {
  const m = type.match(/^(.+?)\[(\d+)\]$/);
  if (m) return { base: m[1], size: parseInt(m[2], 10) };
  return null;
}

/** Returns `{ base }` when `type` is a dynamic-length array `T[]`. */
function isDynamicArray(type: string): { base: string } | null {
  const m = type.match(/^(.+?)\[\]$/);
  if (m) return { base: m[1] };
  return null;
}

// ---------------------------------------------------------------------------
// Core decoder — handles both static and dynamic ABI types
// ---------------------------------------------------------------------------

/**
 * Decode a single ABI-encoded parameter from `data`.
 *
 * @param type   ABI type string, e.g. "uint256", "string", "bytes", "address[]", "uint256[3]"
 * @param data   Full ABI-encoded hex data (with or without "0x" prefix).
 * @param byteOffset  Byte offset into the *head* section where this parameter starts
 *               (default 0).  For dynamic types the word at this position is an
 *               offset pointer into the tail section.
 * @returns The decoded value (bigint for ints, string for address/bytes/string, boolean, or array).
 */
export function decodeParameter(
  type: string,
  data: string,
  byteOffset: number = 0,
): any {
  const hex = stripHexPrefix(data);

  // --- Dynamic types use an offset pointer ---------------------------------
  if (isDynamicType(type)) {
    // The head word at byteOffset is a pointer (offset from the START of the
    // encoded data, i.e. from byte 0) to the dynamic data in the tail.
    const tailOffset = Number(readUint256FromHex(hex, byteOffset));
    return decodeDynamicAtOffset(type, hex, tailOffset);
  }

  // --- Static types are read inline ----------------------------------------
  return decodeStatic(type, hex, byteOffset);
}

/**
 * Decode multiple ABI-encoded parameters.
 *
 * @param types  Array of ABI type strings.
 * @param data   Full ABI-encoded hex data (with or without "0x" prefix).
 * @returns Array of decoded values.
 */
export function decodeParameters(types: string[], data: string): any[] {
  const results: any[] = [];
  let headOffset = 0;
  for (const type of types) {
    results.push(decodeParameter(type, data, headOffset));
    headOffset += 32;
  }
  return results;
}

// ---------------------------------------------------------------------------
// Static-type decoder
// ---------------------------------------------------------------------------

function decodeStatic(type: string, hex: string, byteOffset: number): any {
  const word = readWord(hex, byteOffset);

  // Boolean
  if (type === "bool") {
    return decodeBool(word);
  }

  // Address (20 bytes, right-aligned in the low 20 bytes of the word)
  if (type === "address") {
    return decodeAddress(word);
  }

  // bytesN  (1..32)
  const bytesN = type.match(/^bytes(\d+)$/);
  if (bytesN) {
    const n = parseInt(bytesN[1], 10);
    return "0x" + word.slice(0, n * 2);
  }

  // uintN / intN  (8..256, step 8) — also plain "uint" => uint256
  if (/^u?int(\d+)?$/.test(type)) {
    return decodeUint256(word);
  }

  // Fixed-size static array: T[N] where T is also static
  const fixed = isFixedArray(type);
  if (fixed) {
    const results: any[] = [];
    for (let i = 0; i < fixed.size; i++) {
      results.push(decodeStatic(fixed.base, hex, byteOffset + i * 32));
    }
    return results;
  }

  // Fallback: try uint256
  return decodeUint256(word);
}

// ---------------------------------------------------------------------------
// Dynamic-type decoder
// ---------------------------------------------------------------------------

/**
 * Decode a dynamic value that lives at `tailOffset` inside `hex`.
 */
function decodeDynamicAtOffset(
  type: string,
  hex: string,
  tailOffset: number,
): any {
  // `bytes` and `string` share the same encoding: length + data
  if (type === "bytes" || type === "string") {
    const len = Number(readUint256FromHex(hex, tailOffset));
    const rawHex = hex.slice(
      (tailOffset + 32) * 2,
      (tailOffset + 32 + len) * 2,
    );
    if (type === "string") {
      // Convert hex → UTF-8 string
      const bytes =
        rawHex.match(/.{1,2}/g)?.map((b) => parseInt(b, 16)) ?? [];
      return Buffer.from(bytes).toString("utf-8");
    }
    return "0x" + rawHex;
  }

  // Dynamic-length array: T[]
  const dynArr = isDynamicArray(type);
  if (dynArr) {
    const len = Number(readUint256FromHex(hex, tailOffset));
    const results: any[] = [];
    for (let i = 0; i < len; i++) {
      const elemOffset = tailOffset + 32 + i * 32;
      if (isDynamicType(dynArr.base)) {
        // Each element is an offset pointer relative to the start of the
        // array data section.
        const innerOffset = Number(readUint256FromHex(hex, elemOffset));
        results.push(
          decodeDynamicAtOffset(
            dynArr.base,
            hex,
            tailOffset + 32 + innerOffset,
          ),
        );
      } else {
        results.push(decodeStatic(dynArr.base, hex, elemOffset));
      }
    }
    return results;
  }

  // Fixed-size array where the base type is dynamic: T[N]
  const fixed = isFixedArray(type);
  if (fixed) {
    // Each element is an offset pointer (relative to the start of the array
    // data section), followed by the actual dynamic data.
    const results: any[] = [];
    const offsets: number[] = [];
    for (let i = 0; i < fixed.size; i++) {
      offsets.push(
        Number(readUint256FromHex(hex, tailOffset + 32 + i * 32)),
      );
    }
    for (let i = 0; i < fixed.size; i++) {
      results.push(
        decodeDynamicAtOffset(
          fixed.base,
          hex,
          tailOffset + 32 + offsets[i],
        ),
      );
    }
    return results;
  }

  // Fallback: treat as uint256
  return readUint256FromHex(hex, tailOffset);
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
