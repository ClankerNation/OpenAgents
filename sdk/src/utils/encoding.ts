/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */
import { AbiCoder } from "ethers";

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const abiCoder = AbiCoder.defaultAbiCoder();

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

function normalizeHex(data: string): string {
  return data.startsWith("0x") ? data.slice(2) : data;
}

function getSlotByOffset(data: string, offset: number): string | null {
  const cleaned = normalizeHex(data);
  if (cleaned.length === 0) return null;

  // Backward compatibility: older callers often pass slot index (0, 1, 2...)
  const byWordIndex = offset * 64;
  if (byWordIndex + 64 <= cleaned.length) {
    return cleaned.slice(byWordIndex, byWordIndex + 64);
  }

  // ABI-native behavior: byte offsets.
  const byByteOffset = offset * 2;
  if (byByteOffset + 64 <= cleaned.length) {
    return cleaned.slice(byByteOffset, byByteOffset + 64);
  }

  if (cleaned.length <= 64) {
    return cleaned.padStart(64, "0");
  }

  return null;
}

function decodeStaticSlot(type: string, slot: string): unknown {
  switch (type) {
    case "uint256":
      return decodeUint256(slot);
    case "address":
      return decodeAddress(slot);
    case "bool":
      return decodeBool(slot);
    case "bytes32":
      return "0x" + slot.padStart(64, "0");
    default:
      return undefined;
  }
}

function splitTupleTypes(tupleType: string): string[] {
  const body = tupleType.slice(1, -1).trim();
  if (!body) return [];

  const result: string[] = [];
  let start = 0;
  let depth = 0;

  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if (ch === "(") depth += 1;
    if (ch === ")") depth -= 1;
    if (ch === "," && depth === 0) {
      result.push(body.slice(start, i).trim());
      start = i + 1;
    }
  }
  result.push(body.slice(start).trim());
  return result;
}

function normalizeDecodedValue(type: string, value: any): any {
  const trimmedType = type.trim();

  if (trimmedType === "bytes") {
    const hex = normalizeHex(value);
    return Buffer.from(hex, "hex");
  }

  if (trimmedType.endsWith("[]")) {
    const itemType = trimmedType.slice(0, -2).trim();
    return Array.from(value, (item) => normalizeDecodedValue(itemType, item));
  }

  if (trimmedType.startsWith("(") && trimmedType.endsWith(")")) {
    const tupleTypes = splitTupleTypes(trimmedType);
    return tupleTypes.map((itemType, index) =>
      normalizeDecodedValue(itemType, value[index])
    );
  }

  return value;
}

export function decodeParameter(type: string, data: string, offset = 0): unknown {
  const slot = getSlotByOffset(data, offset);
  if (slot) {
    const staticDecoded = decodeStaticSlot(type, slot);
    if (staticDecoded !== undefined) return staticDecoded;
  }

  const cleaned = normalizeHex(data);
  const encoded = "0x" + cleaned;
  const decoded = abiCoder.decode([type], encoded)[0];
  return normalizeDecodedValue(type, decoded);
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
