// @fix-author rafaio1
// @date 2026-08-24T22:01:00Z
// @runtime linux x64 /tmp/openagents_fix bash
// @platform-config Agentic bounty-hunter workflow
/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | Buffer | Uint8Array | AbiParam[];
  components?: AbiParam[]; // For tuple types
}

const MAX_UINT256 = (1n << 256n) - 1n;

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new RangeError(`encodeUint256: value out of range [0, 2^256-1]: ${n}`);
  }
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
      case "string": {
        const strBytes = Buffer.from(param.value as string, "utf-8");
        const hexStr = strBytes.toString("hex");
        const lenHex = BigInt(strBytes.length).toString(16).padStart(64, "0");
        encoded += lenHex + hexStr.padEnd(Math.ceil(hexStr.length / 64) * 64, "0");
        break;
      }
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  if (!hex.startsWith("0x")) {
    throw new Error(`decodeHex: expected 0x-prefixed hex string, got "${hex}"`);
  }
  const cleaned = hex.slice(2);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error(`decodeHex: invalid hex characters in "${hex}"`);
  }
  return BigInt("0x" + (cleaned || "0"));
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  const value = BigInt("0x" + padded);
  if (value > MAX_UINT256) {
    throw new RangeError(`decodeUint256: decoded value exceeds uint256 max`);
  }
  return value;
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

/**
 * Decode a dynamic string from ABI-encoded hex data.
 * Reads offset (first 32 bytes), then length at offset, then UTF-8 data.
 */
export function decodeString(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
  const length = parseInt(cleaned.slice(offset, offset + 64), 16);
  const strStart = offset + 64;
  const strEnd = strStart + length * 2;
  const hexStr = cleaned.slice(strStart, strEnd);
  return Buffer.from(hexStr, "hex").toString("utf-8");
}

/**
 * Decode dynamic bytes from ABI-encoded hex data.
 * Reads offset, then length, then raw bytes.
 */
export function decodeBytes(data: string): Buffer {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
  const length = parseInt(cleaned.slice(offset, offset + 64), 16);
  const bytesStart = offset + 64;
  const bytesEnd = bytesStart + length * 2;
  const hexBytes = cleaned.slice(bytesStart, bytesEnd);
  return Buffer.from(hexBytes, "hex");
}

/**
 * Decode a dynamic array from ABI-encoded hex data.
 * Reads offset, then length, then each element according to elementType.
 */
export function decodeArray(data: string, elementType: AbiType): unknown[] {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
  const length = parseInt(cleaned.slice(offset, offset + 64), 16);
  const result: unknown[] = [];
  let pos = offset + 64;
  for (let i = 0; i < length; i++) {
    const slot = cleaned.slice(pos, pos + 64);
    switch (elementType) {
      case "uint256":
        result.push(decodeUint256(slot));
        break;
      case "address":
        result.push(decodeAddress(slot));
        break;
      case "bool":
        result.push(decodeBool(slot));
        break;
      case "bytes32":
        result.push("0x" + slot);
        break;
      default:
        result.push("0x" + slot);
        break;
    }
    pos += 64;
  }
  return result;
}

/**
 * Decode a tuple (struct) from ABI-encoded hex data recursively.
 * Each component is decoded according to its type.
 */
export function decodeTuple(data: string, components: AbiParam[]): Record<string, unknown> {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const result: Record<string, unknown> = {};
  let pos = 0;
  for (const comp of components) {
    const slot = cleaned.slice(pos, pos + 64);
    const name = (comp as any).name || `field_${pos}`;
    switch (comp.type) {
      case "uint256":
        result[name] = decodeUint256(slot);
        break;
      case "address":
        result[name] = decodeAddress(slot);
        break;
      case "bool":
        result[name] = decodeBool(slot);
        break;
      case "bytes32":
        result[name] = "0x" + slot;
        break;
      case "string":
        result[name] = decodeString("0x" + cleaned.slice(pos));
        break;
      case "bytes":
        result[name] = decodeBytes("0x" + cleaned.slice(pos));
        break;
      case "tuple":
        if (comp.components) {
          result[name] = decodeTuple("0x" + cleaned.slice(pos), comp.components);
        }
        break;
      default:
        result[name] = "0x" + slot;
        break;
    }
    pos += 64;
  }
  return result;
}

/**
 * Generic decodeParameter: routes to the correct decoder based on type.
 * Handles both fixed-size and dynamic types.
 */
export function decodeParameter(type: AbiType, data: string, components?: AbiParam[]): unknown {
  switch (type) {
    case "uint256":
      return decodeUint256(data);
    case "address":
      return decodeAddress(data);
    case "bool":
      return decodeBool(data);
    case "bytes32":
      return data.startsWith("0x") ? data : "0x" + data;
    case "string":
      return decodeString(data);
    case "bytes":
      return decodeBytes(data);
    case "tuple":
      return components ? decodeTuple(data, components) : data;
    default:
      return data;
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
