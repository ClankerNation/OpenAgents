// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
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

/**
 * Decode a single ABI-encoded parameter from hex data at a given offset.
 * Handles fixed types (uint256, address, bool, bytes32) and dynamic types
 * (string, bytes, arrays) with proper offset resolution per Solidity ABI spec.
 */
export function decodeParameter(
  type: string,
  data: string,
  offset: number = 0
): { value: unknown; nextOffset: number } {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;

  // Dynamic types: read offset pointer, then resolve actual data
  if (type === "string" || type === "bytes") {
    const ptrHex = cleanData.slice(offset * 2, offset * 2 + 64);
    const ptr = parseInt(ptrHex, 16);
    const lenHex = cleanData.slice(ptr * 2, ptr * 2 + 64);
    const len = parseInt(lenHex, 16);
    const rawHex = cleanData.slice(ptr * 2 + 64, ptr * 2 + 64 + len * 2);

    if (type === "string") {
      const buf = Buffer.from(rawHex, "hex");
      return { value: buf.toString("utf-8"), nextOffset: offset + 32 };
    } else {
      return { value: Buffer.from(rawHex, "hex"), nextOffset: offset + 32 };
    }
  }

  // Dynamic array: T[]
  if (type.endsWith("[]")) {
    const elementType = type.slice(0, -2);
    const ptrHex = cleanData.slice(offset * 2, offset * 2 + 64);
    const ptr = parseInt(ptrHex, 16);
    const lenHex = cleanData.slice(ptr * 2, ptr * 2 + 64);
    const len = parseInt(lenHex, 16);

    const arr: unknown[] = [];
    let elemOffset = ptr + 32; // skip length word
    for (let i = 0; i < len; i++) {
      const result = decodeParameter(elementType, data, elemOffset);
      arr.push(result.value);
      // For fixed-size elements, advance by 32 bytes; for dynamic, the sub-decode handles its own offset
      if (isDynamicType(elementType)) {
        // Dynamic elements store offset pointers sequentially
        elemOffset += 32;
      } else {
        elemOffset += 32;
      }
    }
    return { value: arr, nextOffset: offset + 32 };
  }

  // Tuple: (type1,type2,...)
  if (type.startsWith("(") && type.endsWith(")")) {
    const innerTypes = parseTupleTypes(type.slice(1, -1));
    const tupleResult: Record<string, unknown> = {};
    let currentOffset = offset;

    for (let i = 0; i < innerTypes.length; i++) {
      const result = decodeParameter(innerTypes[i], data, currentOffset);
      tupleResult[`field${i}`] = result.value;
      currentOffset = isDynamicType(innerTypes[i]) ? currentOffset + 32 : currentOffset + 32;
    }
    return { value: tupleResult, nextOffset: currentOffset };
  }

  // Fixed-size types
  const slot = cleanData.slice(offset * 2, offset * 2 + 64);

  switch (type) {
    case "uint256":
    case "uint128":
    case "uint64":
    case "uint32":
    case "uint16":
    case "uint8":
      return { value: BigInt("0x" + slot), nextOffset: offset + 32 };
    case "int256": {
      const val = BigInt("0x" + slot);
      // Handle signed integers via two's complement
      const max = 1n << 255n;
      return { value: val >= max ? val - (1n << 256n) : val, nextOffset: offset + 32 };
    }
    case "address":
      return { value: "0x" + slot.slice(24).toLowerCase(), nextOffset: offset + 32 };
    case "bool":
      return { value: BigInt("0x" + slot) !== 0n, nextOffset: offset + 32 };
    case "bytes32":
      return { value: "0x" + slot, nextOffset: offset + 32 };
    default:
      // Unknown type: return raw hex slot
      return { value: "0x" + slot, nextOffset: offset + 32 };
  }
}

function isDynamicType(type: string): boolean {
  return type === "string" || type === "bytes" || type.endsWith("[]") ||
    (type.startsWith("(") && type.endsWith(")"));
}

function parseTupleTypes(inner: string): string[] {
  const types: string[] = [];
  let depth = 0;
  let current = "";
  for (const ch of inner) {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    if (ch === "," && depth === 0) {
      types.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  if (current.trim()) types.push(current.trim());
  return types;
}
