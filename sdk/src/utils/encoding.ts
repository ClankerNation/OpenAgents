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
  if (!hex.startsWith("0x")) throw new Error("Hex string must start with 0x");
  const cleaned = hex.slice(2);
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned.padStart(64, "0"));
}

export function decodeAddress(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const raw = cleaned.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned) !== 0n;
}

export function decodeString(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
  const length = parseInt(cleaned.slice(offset, offset + 64), 16) * 2;
  const raw = cleaned.slice(offset + 64, offset + 64 + length);
  return Buffer.from(raw, "hex").toString("utf-8");
}

export function decodeBytes(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
  const length = parseInt(cleaned.slice(offset, offset + 64), 16) * 2;
  return "0x" + cleaned.slice(offset + 64, offset + 64 + length);
}

export function decodeDynamicArray(slot: string, elementType: AbiType): unknown[] {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
  const length = parseInt(cleaned.slice(offset, offset + 64), 16);
  const result: unknown[] = [];
  for (let i = 0; i < length; i++) {
    const start = offset + 64 + i * 64;
    const raw = cleaned.slice(start, start + 64);
    switch (elementType) {
      case "uint256": result.push(BigInt("0x" + raw)); break;
      case "address": result.push("0x" + raw.slice(-40).toLowerCase()); break;
      case "bool": result.push(BigInt("0x" + raw) !== 0n); break;
      case "string": result.push(decodeString("0x" + raw)); break;
      default: result.push("0x" + raw);
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
