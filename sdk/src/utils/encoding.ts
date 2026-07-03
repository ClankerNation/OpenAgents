/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author hermes-agent (scotia1973-bot)
 * @fix-description Added decodeParameter with full dynamic ABI type support:
 *   string, bytes, dynamic arrays, tuples, and nested compound types
 * @fix-issue #198
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

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

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}

// =============================================================================
// Dynamic ABI Decoding — Added for bounty #198
// =============================================================================

/**
 * Read a 32-byte slot (64 hex chars) from the data at the given byte offset.
 */
function readSlot(data: string, byteOffset: number): string {
  return data.slice(byteOffset * 2, byteOffset * 2 + 64);
}

/**
 * Convert a 32-byte hex slot to a BigInt.
 */
function slotToBigInt(slot: string): bigint {
  return BigInt("0x" + slot);
}

/**
 * Determine if an ABI type is dynamically sized (needs head/tail pointer encoding).
 */
function isDynamicType(type: string): boolean {
  const base = type.replace(/\[\]$/, "");
  if (type.endsWith("[]")) return true;
  if (base.startsWith("(")) {
    const inners = parseTupleTypes(base);
    return inners.some(isDynamicType);
  }
  return base === "string" || base === "bytes";
}

/**
 * Get the static byte size of an ABI type (32 for fixed types).
 * For dynamic types, returns 32 (the pointer slot).
 */
function staticByteSize(type: string): number {
  if (type.endsWith("[]") || type === "string" || type === "bytes") return 32;
  if (type.startsWith("(")) {
    const inners = parseTupleTypes(type);
    let total = 0;
    for (const inner of inners) {
      total += isDynamicType(inner) ? 32 : staticByteSize(inner);
    }
    return total;
  }
  return 32;
}

/**
 * Parse a tuple type string into its component type strings.
 * Handles nested parentheses and array suffixes correctly.
 *
 * Example: "(uint256,address,bool)" → ["uint256", "address", "bool"]
 * Example: "(uint256,(address,string))" → ["uint256", "(address,string)"]
 * Example: "uint256[],address[],bool" → ["uint256[]", "address[]", "bool"]
 */
export function parseTupleTypes(typeStr: string): string[] {
  const s = typeStr.startsWith("(") && typeStr.endsWith(")") ? typeStr.slice(1, -1) : typeStr;
  const result: string[] = [];
  let depth = 0;
  let current = "";

  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === "(") {
      depth++;
      current += ch;
    } else if (ch === ")") {
      depth--;
      current += ch;
    } else if (ch === "," && depth === 0) {
      result.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  if (current.trim()) {
    result.push(current.trim());
  }
  return result;
}

/**
 * Decode a static elementary type from a specific byte offset.
 * Does NOT handle pointer resolution — reads data directly at the offset.
 */
function decodeStaticAt(
  type: string,
  hex: string,
  offset: number,
): bigint | string | boolean {
  if (type === "uint256" || type === "int256" || type === "uint" || type === "int") {
    return slotToBigInt(readSlot(hex, offset));
  }
  if (type === "address") {
    const raw = readSlot(hex, offset).slice(-40);
    return "0x" + raw.toLowerCase();
  }
  if (type === "bool") {
    return slotToBigInt(readSlot(hex, offset)) !== 0n;
  }
  if (type === "bytes32") {
    return "0x" + readSlot(hex, offset);
  }
  const bytesNMatch = type.match(/^bytes(\d+)$/);
  if (bytesNMatch) {
    const n = parseInt(bytesNMatch[1], 10);
    return "0x" + readSlot(hex, offset).slice(0, n * 2);
  }
  throw new Error(`Unsupported static ABI type: ${type}`);
}

/**
 * Decode a dynamic type's DATA starting at the given byte offset.
 * The offset is expected to point directly to the element's data
 * (not to a pointer slot). For strings/bytes this means [length][data].
 * For arrays this means [length][elements].
 * For tuples this means [tuple_head][tuple_tail].
 */
function decodeDynamicData(
  type: string,
  hex: string,
  dataOffset: number,
): string | Array<unknown> {
  // --- string ---
  if (type === "string") {
    const length = Number(slotToBigInt(readSlot(hex, dataOffset)));
    if (length === 0) return "";
    const rawHex = hex.slice(dataOffset * 2 + 64, dataOffset * 2 + 64 + length * 2);
    const bytes = Buffer.from(rawHex, "hex");
    return bytes.toString("utf8");
  }

  // --- bytes ---
  if (type === "bytes") {
    const length = Number(slotToBigInt(readSlot(hex, dataOffset)));
    if (length === 0) return "0x";
    const rawHex = hex.slice(dataOffset * 2 + 64, dataOffset * 2 + 64 + length * 2);
    return "0x" + rawHex;
  }

  // --- Dynamic array: type[] ---
  if (type.endsWith("[]")) {
    const elemType = type.slice(0, -2);
    const length = Number(slotToBigInt(readSlot(hex, dataOffset)));
    const result: Array<unknown> = [];
    const elemIsDynamic = isDynamicType(elemType);
    const elemSize = elemIsDynamic ? 32 : staticByteSize(elemType);
    let elemSlotOffset = dataOffset + 32; // after length

    for (let i = 0; i < length; i++) {
      if (elemIsDynamic) {
        // Read relative pointer from the slot, resolve it relative to dataOffset
        const relPtr = Number(slotToBigInt(readSlot(hex, elemSlotOffset)));
        result.push(decodeDynamicData(elemType, hex, dataOffset + relPtr));
      } else {
        result.push(decodeStaticAt(elemType, hex, elemSlotOffset));
      }
      elemSlotOffset += elemIsDynamic ? 32 : elemSize;
    }
    return result;
  }

  // --- Tuple: (type1,type2,...) ---
  if (type.startsWith("(")) {
    const innerTypes = parseTupleTypes(type);
    const result: Array<unknown> = [];
    let headOffset = dataOffset;

    for (let i = 0; i < innerTypes.length; i++) {
      const t = innerTypes[i];
      if (isDynamicType(t)) {
        // Read relative pointer from the head, resolve relative to dataOffset
        const relPtr = Number(slotToBigInt(readSlot(hex, headOffset)));
        result.push(decodeDynamicData(t, hex, dataOffset + relPtr));
        headOffset += 32;
      } else {
        result.push(decodeStaticAt(t, hex, headOffset));
        headOffset += staticByteSize(t);
      }
    }
    return result;
  }

  throw new Error(`Unsupported ABI type: ${type}`);
}

/**
 * Decode a single ABI parameter from hex-encoded calldata/return data.
 *
 * Supports:
 *   - Static types: uint256, address, bool, bytes32, bytesN
 *   - Dynamic types: string, bytes
 *   - Dynamic arrays: type[] (e.g. uint256[], address[])
 *   - Tuples: (type1,type2,...) — both static and dynamic
 *   - Arrays of tuples: (type1,type2)[]
 *
 * @param type  The ABI type string (e.g. "uint256", "string", "address[]", "(uint256,bool)")
 * @param data  Hex-encoded data (may include 0x prefix)
 * @param offset  Byte offset into data where this parameter's slot begins
 * @returns The decoded value (bigint, string, boolean, Array, or nested structure)
 */
export function decodeParameter(
  type: string,
  data: string,
  offset: number,
): bigint | string | boolean | Array<unknown> {
  const hex = data.startsWith("0x") ? data.slice(2) : data;

  // Static elementary types — read directly at offset
  if (
    type === "uint256" || type === "int256" || type === "uint" || type === "int" ||
    type === "address" || type === "bool" || type === "bytes32" ||
    /^bytes\d+$/.test(type)
  ) {
    return decodeStaticAt(type, hex, offset);
  }

  // Dynamic elementary types — the slot at `offset` contains a POINTER to the data
  if (type === "string" || type === "bytes" || type.endsWith("[]")) {
    const ptr = Number(slotToBigInt(readSlot(hex, offset)));
    return decodeDynamicData(type, hex, ptr);
  }

  // Tuple — check if it's dynamic (needs pointer) or static (inline)
  if (type.startsWith("(")) {
    if (isDynamicType(type)) {
      const ptr = Number(slotToBigInt(readSlot(hex, offset)));
      return decodeDynamicData(type, hex, ptr);
    }
    // Static tuple: data is inline at offset
    return decodeDynamicData(type, hex, offset);
  }

  throw new Error(`Unsupported ABI type: ${type}`);
}
