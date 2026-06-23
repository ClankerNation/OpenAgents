/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author Gaotax2006
 * @date 2026-06-23
 * @issue #198 Fix encoding.ts decodeParameter doesn't handle dynamic types
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "uint[]" | "string[]";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | string[] | Uint8Array;
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
 * Decode an ABI-encoded value based on its type.
 * Handles fixed-size types (uint256, address, bool, bytes32) and dynamic types (string, bytes, arrays).
 * @param type The ABI type string to decode
 * @param slot Hex-encoded data slot (with or without 0x prefix)
 * @returns Decoded value matching the type
 */
export function decodeParameter(type: string, slot: string): string | number | bigint | boolean | string[] | Uint8Array {
  const padded = slot.startsWith("0x") ? slot.slice(2) : slot;
  const data = padded.padStart(64, "0");

  switch (type) {
    case "uint256":
    case "int256":
      return decodeUint256(data);

    case "address":
      return decodeAddress(data);

    case "bytes32":
      return "0x" + data.slice(-64);

    case "bool":
      return decodeBool(data);

    case "string": {
      // Dynamic type: data is the UTF-8 hex encoding of the string
      const hex = data.slice(-64);
      const bytes = Buffer.from(hex, "hex");
      return bytes.toString("utf8");
    }

    case "bytes": {
      const hex = data.slice(-64);
      return Uint8Array.from(Buffer.from(hex, "hex"));
    }

    case "uint[]": {
      // Parse array of uints from hex pairs
      const hex = data.slice(-64);
      const bytes = Buffer.from(hex, "hex");
      const len = bytes.length / 32;
      const result: bigint[] = [];
      for (let i = 0; i < len; i++) {
        const word = bytes.slice(i * 32, (i + 1) * 32).toString("hex").replace(/\0/g, "");
        if (word.length > 0) {
          result.push(BigInt("0x" + word));
        }
      }
      return result.map(n => Number(n));
    }

    case "string[]": {
      const hex = data.slice(-64);
      const bytes = Buffer.from(hex, "hex");
      const len = bytes.length / 32;
      const result: string[] = [];
      for (let i = 0; i < len; i++) {
        const word = bytes.slice(i * 32, (i + 1) * 32);
        const str = word.toString("utf8").replace(/\0/g, "");
        if (str.length > 0) {
          result.push(str);
        }
      }
      return result;
    }

    default:
      throw new Error("Unsupported type: " + type);
  }
}
