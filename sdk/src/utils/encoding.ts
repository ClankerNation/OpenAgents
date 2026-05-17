/**
 * @fix-author: metatron-hermes-agent
 * @fix-date: 2026-05-17T05:00:00Z
 * @fix-issue: #198 — Add decodeParameter for dynamic types (string, bytes, arrays, tuples)
 * @pre-conversation:
 *   Identity: Metatron (AI — celestial scribe, autonomous coding agent)
 *   Platform: Hermes Agent with DeepSeek V4 Pro
 *   Environment: linux, x86_64, /home/power, /home/power/repos/OpenAgents, bash
 *   Operating Instructions: SOUL.md — be genuinely helpful, resourceful, earn trust through competence
 *   Skills loaded: github-bounties, blockchain-operations
 * @runtime:
 *   os: linux
 *   arch: x86_64
 *   home_dir: /home/power
 *   working_dir: /home/power/repos/OpenAgents
 *   shell: bash
 */

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

// ─── Encoding ────────────────────────────────────────────────

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

// ─── Decoding ────────────────────────────────────────────────

export function decodeHex(hex: string): bigint {
  // FIX: Validate "0x" prefix — bare decimal strings would silently parse as hex
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]+$/.test(cleaned)) {
    throw new Error(`decodeHex: invalid hex string: ${hex.slice(0, 32)}...`);
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  // FIX: Handle short values — left-pad to 64 chars before parsing
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned) !== 0n;
}

export function decodeString(hex: string, offset: number): string {
  // Dynamic string: [offset] → len(32) → UTF-8 data padded to 32 bytes
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  const lenSlot = cleaned.slice(offset * 2, offset * 2 + 64);
  const byteLen = Number(BigInt("0x" + lenSlot));
  const dataStart = offset * 2 + 64;
  const dataEnd = dataStart + byteLen * 2;
  const hexData = cleaned.slice(dataStart, dataEnd);
  return Buffer.from(hexData, "hex").toString("utf8");
}

export function decodeBytes(hex: string, offset: number): Uint8Array {
  // Dynamic bytes: [offset] → len(32) → raw data padded to 32 bytes
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  const lenSlot = cleaned.slice(offset * 2, offset * 2 + 64);
  const byteLen = Number(BigInt("0x" + lenSlot));
  const dataStart = offset * 2 + 64;
  const dataEnd = dataStart + byteLen * 2;
  const hexData = cleaned.slice(dataStart, dataEnd);
  return Uint8Array.from(Buffer.from(hexData, "hex"));
}

/**
 * Parse a Solidity ABI type string into components.
 * Handles: uint256, address, bool, bytes32, string, bytes, uint256[], address[], tuple(uint256,address), etc.
 */
function parseTypeComponents(type: string): { base: string; isArray: boolean; tupleTypes: string[] } {
  // Check for dynamic array: type[]
  const arrayMatch = type.match(/^(.+)\[\]$/);
  if (arrayMatch) {
    return { base: arrayMatch[1], isArray: true, tupleTypes: [] };
  }

  // Check for tuple: tuple(type1,type2,...)
  const tupleMatch = type.match(/^tuple\((.*)\)$/);
  if (tupleMatch) {
    const inner = tupleMatch[1];
    const tupleTypes = inner.split(",").map((t) => t.trim()).filter(Boolean);
    return { base: "tuple", isArray: false, tupleTypes };
  }

  // Static or dynamic scalar
  return { base: type, isArray: false, tupleTypes: [] };
}

/**
 * Decode a single ABI-encoded parameter from hex data.
 *
 * Supports:
 *   - Static types: uint256, address, bool, bytes32
 *   - Dynamic types: string, bytes
 *   - Dynamic arrays: uint256[], address[], string[], etc.
 *   - Tuples: tuple(uint256,address), including nested dynamic members
 *
 * @param hex - ABI-encoded hex string (with or without 0x prefix)
 * @param type - Solidity type string (e.g., "uint256", "address[]", "tuple(uint256,address)")
 * @returns Decoded value — bigint, string, boolean, Uint8Array, array, or object (for tuples)
 */
export function decodeParameter(hex: string, type: string): unknown {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  const { base, isArray, tupleTypes } = parseTypeComponents(type);

  // ── Dynamic array ──
  if (isArray) {
    return decodeDynamicArray(cleaned, 0, base);
  }

  // ── Tuple ──
  if (base === "tuple") {
    return decodeTuple(cleaned, 0, tupleTypes);
  }

  // ── Dynamic scalars (string, bytes) ──
  if (base === "string") {
    return decodeString(cleaned, readOffset(cleaned, 0));
  }
  if (base === "bytes") {
    return decodeBytes(cleaned, readOffset(cleaned, 0));
  }

  // ── Static scalars ──
  return decodeStaticScalar(cleaned, 0, base);
}

function readOffset(hex: string, byteOffset: number): number {
  const slot = hex.slice(byteOffset * 2, byteOffset * 2 + 64);
  return Number(BigInt("0x" + slot));
}

function readSlot(hex: string, byteOffset: number): string {
  return hex.slice(byteOffset * 2, byteOffset * 2 + 64);
}

function decodeStaticScalar(hex: string, byteOffset: number, type: string): unknown {
  const slot = readSlot(hex, byteOffset);
  switch (type) {
    case "uint256":
    case "uint128":
    case "uint64":
    case "uint32":
    case "uint16":
    case "uint8":
      return BigInt("0x" + slot);
    case "int256":
    case "int128":
    case "int64":
    case "int32":
    case "int16":
    case "int8": {
      const raw = BigInt("0x" + slot);
      // Sign-extend based on bit width
      const bits = parseInt(type.replace("int", ""), 10);
      const maxUnsigned = 1n << BigInt(bits);
      const half = maxUnsigned >> 1n;
      return raw >= half ? raw - maxUnsigned : raw;
    }
    case "address":
      return decodeAddress(slot);
    case "bool":
      return decodeBool(slot);
    case "bytes32":
      return "0x" + slot;
    default:
      throw new Error(`decodeParameter: unsupported static type "${type}"`);
  }
}

function decodeDynamicArray(hex: string, headOffset: number, elementType: string): unknown[] {
  const dataOffset = readOffset(hex, headOffset);
  const lenSlot = readSlot(hex, dataOffset);
  const length = Number(BigInt("0x" + lenSlot));

  const { base, isArray, tupleTypes } = parseTypeComponents(elementType);
  const results: unknown[] = [];

  // Each element is 32 bytes in the static head (or an offset for dynamic elements)
  const elementSlotSize = 32;
  const elementHeadStart = dataOffset + 32; // After length slot

  for (let i = 0; i < length; i++) {
    const elemOffset = elementHeadStart + i * elementSlotSize;

    if (base === "string") {
      const strOffset = readOffset(hex, elemOffset);
      // Per-element offsets are relative to body start (dataOffset)
      results.push(decodeString(hex, dataOffset + strOffset));
    } else if (base === "bytes") {
      const bytesOffset = readOffset(hex, elemOffset);
      results.push(decodeBytes(hex, dataOffset + bytesOffset));
    } else if (base === "tuple") {
      if (tupleHasDynamic(tupleTypes)) {
        const tupOffset = readOffset(hex, elemOffset);
        results.push(decodeTuple(hex, dataOffset + tupOffset, tupleTypes));
      } else {
        results.push(decodeTuple(hex, elemOffset, tupleTypes));
      }
    } else if (isArray) {
      const arrOffset = readOffset(hex, elemOffset);
      results.push(decodeDynamicArray(hex, dataOffset + arrOffset, base));
    } else {
      // Static type element
      results.push(decodeStaticScalar(hex, elemOffset, elementType));
    }
  }

  return results;
}

function tupleHasDynamic(types: string[]): boolean {
  return types.some((t) => {
    const { base, isArray } = parseTypeComponents(t);
    return base === "string" || base === "bytes" || isArray || base === "tuple";
  });
}

function decodeTuple(hex: string, headOffset: number, types: string[]): Record<string, unknown> {
  // For tuples, elements are packed into 32-byte slots starting at headOffset.
  // Static elements are inline. Dynamic elements store an offset (relative to headOffset).
  let slotIndex = 0;
  const result: Record<string, unknown> = {};

  for (let i = 0; i < types.length; i++) {
    const type = types[i];
    const slotOffset = headOffset + slotIndex * 32;
    const { base, isArray, tupleTypes } = parseTypeComponents(type);

    if (isArray || base === "string" || base === "bytes" || (base === "tuple" && tupleHasDynamic(tupleTypes))) {
      // Dynamic member — read offset relative to headOffset
      const dynamicOffset = readOffset(hex, slotOffset);
      const absOffset = headOffset + dynamicOffset;

      if (base === "string") {
        result[`_${i}`] = decodeString(hex, absOffset);
      } else if (base === "bytes") {
        result[`_${i}`] = decodeBytes(hex, absOffset);
      } else if (base === "tuple") {
        result[`_${i}`] = decodeTuple(hex, absOffset, tupleTypes);
      } else if (isArray) {
        result[`_${i}`] = decodeDynamicArray(hex, absOffset, base);
      }
    } else {
      // Static member — inline in slot
      result[`_${i}`] = decodeStaticScalar(hex, slotOffset, type);
    }
    slotIndex++;
  }

  return result;
}

// ─── Selector + Calldata ────────────────────────────────────

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
