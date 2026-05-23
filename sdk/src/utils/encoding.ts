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
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  return BigInt("0x" + slot);
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

export function decodeString(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
  const length = parseInt(cleaned.slice(offset, offset + 64), 16) * 2;
  const raw = cleaned.slice(offset + 64, offset + 64 + length);
  return Buffer.from(raw, "hex").toString("utf8");
}

export function decodeBytes(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
  const length = parseInt(cleaned.slice(offset, offset + 64), 16) * 2;
  return "0x" + cleaned.slice(offset + 64, offset + 64 + length);
}

export function decodeDynamicArray(slot: string, decodeFn: (s: string) => any): any[] {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const length = parseInt(cleaned.slice(0, 64), 16);
  const result: any[] = [];
  for (let i = 0; i < length; i++) {
    result.push(decodeFn(cleaned.slice(64 + i * 64, 64 + (i + 1) * 64)));
  }
  return result;
}

export function decodeParameter(type: string, slot: string): any {
  const fixed = slot.startsWith("0x") ? slot : "0x" + slot;
  switch (type) {
    case "uint256": return decodeUint256(fixed);
    case "address": return decodeAddress(fixed);
    case "bool": return decodeBool(fixed);
    case "string": return decodeString(fixed);
    case "bytes": return decodeBytes(fixed);
    default: return fixed;
  }
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
