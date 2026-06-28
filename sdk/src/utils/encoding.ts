/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * Supports fixed types (uint256, address, bytes32, bool) and dynamic types
 * (string, bytes, arrays, tuples) following the Ethereum ABI specification.
 */

export type AbiType =
  | "uint256"
  | "address"
  | "bytes32"
  | "string"
  | "bool"
  | "bytes"
  | "uint256[]"
  | "address[]"
  | "string[]"
  | "bytes[]";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | (string | number | bigint)[];
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

export function decodeParameter(hex: string, type: AbiType): unknown {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;

  switch (type) {
    case "uint256":
      return decodeUint256(cleaned);
    case "address":
      return decodeAddress(cleaned);
    case "bytes32":
      return "0x" + cleaned.slice(0, 64);
    case "bool":
      return decodeBool(cleaned);
    case "string":
      return decodeString(cleaned);
    case "bytes":
      return decodeBytes(cleaned);
    case "uint256[]":
      return decodeDynamicArray(cleaned, "uint256") as bigint[];
    case "address[]":
      return decodeDynamicArray(cleaned, "address") as string[];
    case "string[]":
      return decodeDynamicArray(cleaned, "string") as string[];
    case "bytes[]":
      return decodeDynamicArray(cleaned, "bytes") as Uint8Array[];
    default:
      throw new Error(`Unsupported type: ${type}`);
  }
}

function decodeString(hex: string): string {
  const offset = parseInt(hex.slice(0, 64), 16) * 2;
  const length = parseInt(hex.slice(offset, offset + 64), 16) * 2;
  const data = hex.slice(offset + 64, offset + 64 + length);
  const bytes = new Uint8Array(data.match(/.{1,2}/g)!.map((b) => parseInt(b, 16)));
  return new TextDecoder().decode(bytes);
}

function decodeBytes(hex: string): Uint8Array {
  const offset = parseInt(hex.slice(0, 64), 16) * 2;
  const length = parseInt(hex.slice(offset, offset + 64), 16) * 2;
  const data = hex.slice(offset + 64, offset + 64 + length);
  const bytes = new Uint8Array(data.match(/.{1,2}/g)!.map((b) => parseInt(b, 16)));
  return bytes;
}

function decodeDynamicArray(hex: string, elementType: string): unknown[] {
  const offset = parseInt(hex.slice(0, 64), 16) * 2;
  const length = parseInt(hex.slice(offset, offset + 64), 16);
  const results: unknown[] = [];
  let currentOffset = offset + 64;

  for (let i = 0; i < length; i++) {
    const slot = hex.slice(currentOffset, currentOffset + 64);
    results.push(decodeParameter("0x" + slot, elementType as AbiType));
    currentOffset += 64;
  }

  return results;
}

function decodeTuple(hex: string, types: AbiType[]): unknown[] {
  const results: unknown[] = [];
  let offset = 0;

  for (const type of types) {
    const slot = hex.slice(offset, offset + 64);
    if (isDynamicType(type)) {
      const dynOffset = parseInt(slot, 16) * 2;
      results.push(decodeParameter("0x" + hex.slice(dynOffset, dynOffset + 64), type));
      offset += 64;
    } else {
      results.push(decodeParameter("0x" + slot, type));
      offset += 64;
    }
  }

  return results;
}

function isDynamicType(type: AbiType): boolean {
  return ["string", "bytes", "string[]", "bytes[]", "uint256[]", "address[]"].includes(type);
}
