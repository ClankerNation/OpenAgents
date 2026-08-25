/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * @fix-author rafaio1
 * @date 2026-08-25T00:00:00Z
 * @runtime linux x64 /tmp/openagents_issue_198 bash
 * @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement
 */

import { createHash } from "crypto";

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const MAX_UINT256 = BigInt("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");

/**
 * Encode a uint256 value to 32-byte hex string
 * @throws Error if value exceeds uint256 max or is negative
 */
export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new Error(`uint256 overflow: ${n.toString()}`);
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error(`Invalid address format: ${address}`);
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length > 64) {
    throw new Error("bytes32 data exceeds 32 bytes");
  }
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

/**
 * Encode dynamic bytes/string using ABI dynamic type encoding
 * Format: offset (32 bytes) + length (32 bytes) + padded data
 */
function encodeDynamicString(value: string): string {
  const hexStr = Buffer.from(value, "utf8").toString("hex");
  const lengthHex = BigInt(hexStr.length / 2).toString(16).padStart(64, "0");
  const paddedData = hexStr.padEnd(Math.ceil(hexStr.length / 64) * 64, "0");
  return lengthHex + paddedData;
}

function encodeDynamicBytes(value: string): string {
  const cleaned = value.startsWith("0x") ? value.slice(2) : value;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("Invalid hex bytes");
  }
  const byteLength = cleaned.length / 2;
  const lengthHex = BigInt(byteLength).toString(16).padStart(64, "0");
  const paddedData = cleaned.padEnd(Math.ceil(cleaned.length / 64) * 64, "0");
  return lengthHex + paddedData;
}

/**
 * Encode parameters following ABI specification with proper dynamic type handling
 * Static types are encoded in-place, dynamic types use offset-based encoding
 */
export function encodeParams(params: AbiParam[]): string {
  let head = "";
  let tail = "";
  let dynamicOffset = params.length * 32;

  for (const param of params) {
    switch (param.type) {
      case "uint256":
        head += encodeUint256(BigInt(param.value as number));
        break;
      case "address":
        head += encodeAddress(param.value as string);
        break;
      case "bytes32":
        head += encodeBytes32(param.value as string);
        break;
      case "bool":
        head += encodeBool(param.value as boolean);
        break;
      case "string": {
        // Dynamic type: store offset in head, actual data in tail
        head += BigInt(dynamicOffset).toString(16).padStart(64, "0");
        const encoded = encodeDynamicString(param.value as string);
        tail += encoded;
        dynamicOffset += (encoded.length / 2);
        break;
      }
      case "bytes": {
        // Dynamic type: store offset in head, actual data in tail
        head += BigInt(dynamicOffset).toString(16).padStart(64, "0");
        const encoded = encodeDynamicBytes(param.value as string);
        tail += encoded;
        dynamicOffset += (encoded.length / 2);
        break;
      }
      default:
        throw new Error(`Unsupported ABI type: ${param.type}`);
    }
  }

  return "0x" + head + tail;
}

/**
 * Decode hex string to bigint with strict validation
 * @throws Error if input is not valid hex
 */
export function decodeHex(hex: string): bigint {
  if (!hex) throw new Error("Empty hex string");
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]+$/.test(cleaned)) {
    throw new Error(`Invalid hex characters: ${hex}`);
  }
  return BigInt("0x" + cleaned);
}

/**
 * Decode uint256 from 32-byte slot with padding validation
 */
export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  if (cleaned.length === 0 || cleaned.length > 64) {
    throw new Error(`Invalid uint256 slot length: ${cleaned.length}`);
  }
  return BigInt("0x" + cleaned.padStart(64, "0"));
}

export function decodeAddress(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  if (cleaned.length < 40) {
    throw new Error("Slot too short for address");
  }
  const raw = cleaned.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return decodeUint256(slot) !== 0n;
}

/**
 * Decode dynamic string from ABI-encoded data at given offset
 */
export function decodeString(data: string, offset: number): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const offsetHex = cleaned.substr(offset * 2, 64);
  const byteOffset = Number(BigInt("0x" + offsetHex));
  
  const lengthHex = cleaned.substr(byteOffset * 2, 64);
  const length = Number(BigInt("0x" + lengthHex));
  
  const dataStart = (byteOffset + 32) * 2;
  const hexData = cleaned.substr(dataStart, length * 2);
  
  return Buffer.from(hexData, "hex").toString("utf8");
}

export function functionSelector(signature: string): string {
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
