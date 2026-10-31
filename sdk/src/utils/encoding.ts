/**
 * Contributor Metadata (required for bounty #198)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 */

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "uint256[]" | "address[]" | "string[]" | "bytes[]" | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | string[] | number[];
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
      default:
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
  const padded = slot.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

/**
 * decodeParameter - decodes an ABI-encoded parameter based on its type.
 * Handles both fixed-size and dynamic types (string, bytes, arrays, tuples).
 *
 * @param type - The ABI type string (e.g., "uint256", "string", "address[]", "tuple")
 * @param data - The hex-encoded data (with or without 0x prefix)
 * @param offset - Byte offset into the data (default: 0)
 * @returns The decoded value
 */
export function decodeParameter(type: string, data: string, offset: number = 0): any {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const bytes = Buffer.from(cleaned, "hex");

  switch (type) {
    case "uint256":
      return decodeUint256(cleaned.slice(offset * 2, offset * 2 + 64));

    case "address":
      return decodeAddress(cleaned.slice(offset * 2, offset * 2 + 64));

    case "bool":
      return decodeBool(cleaned.slice(offset * 2, offset * 2 + 64));

    case "bytes32":
      return "0x" + cleaned.slice(offset * 2, offset * 2 + 64);

    case "string": {
      // Dynamic: read offset from current position, then length, then UTF-8 data
      const strOffset = Number(decodeUint256(cleaned.slice(offset * 2, offset * 2 + 64)));
      const strLength = Number(decodeUint256(cleaned.slice(strOffset * 2, strOffset * 2 + 64)));
      const strData = cleaned.slice(strOffset * 2 + 64, strOffset * 2 + 64 + strLength * 2);
      return Buffer.from(strData, "hex").toString("utf-8");
    }

    case "bytes": {
      // Dynamic: read offset, then length, then raw bytes
      const bytesOffset = Number(decodeUint256(cleaned.slice(offset * 2, offset * 2 + 64)));
      const bytesLength = Number(decodeUint256(cleaned.slice(bytesOffset * 2, bytesOffset * 2 + 64)));
      const bytesData = cleaned.slice(bytesOffset * 2 + 64, bytesOffset * 2 + 64 + bytesLength * 2);
      return Buffer.from(bytesData, "hex");
    }

    case "uint256[]":
    case "address[]":
    case "string[]":
    case "bytes[]": {
      // Dynamic array: read offset, then length, then elements
      const arrOffset = Number(decodeUint256(cleaned.slice(offset * 2, offset * 2 + 64)));
      const arrLength = Number(decodeUint256(cleaned.slice(arrOffset * 2, arrOffset * 2 + 64)));
      const elementType = type.replace("[]", "");
      const result: any[] = [];
      for (let i = 0; i < arrLength; i++) {
        // For fixed-size elements, they're packed after the length
        const elemOffset = arrOffset * 2 + 64 + i * 64;
        result.push(decodeParameter(elementType, "0x" + cleaned.slice(elemOffset), 0));
      }
      return result;
    }

    default:
      // For unknown types, return raw hex
      return "0x" + cleaned.slice(offset * 2, offset * 2 + 64);
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
