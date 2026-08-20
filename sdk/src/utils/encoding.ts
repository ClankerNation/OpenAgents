// @contributor rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "int256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const MAX_UINT256 = (1n << 256n) - 1n;

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new Error(`encodeUint256: value out of uint256 range [0, 2^256-1]: ${n}`);
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

const MIN_INT256 = -(1n << 255n);
const MAX_INT256 = (1n << 255n) - 1n;

export function encodeInt256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < MIN_INT256 || n > MAX_INT256) {
    throw new Error(`encodeInt256: value out of int256 range: ${n}`);
  }
  if (n >= 0n) {
    return n.toString(16).padStart(64, "0");
  }
  // Two's complement for negative values
  const twosComplement = (1n << 256n) + n;
  return twosComplement.toString(16).padStart(64, "0");
}

export function encodeParams(params: AbiParam[]): string {
  let encoded = "0x";
  for (const param of params) {
    switch (param.type) {
      case "uint256":
        encoded += encodeUint256(BigInt(param.value as number));
        break;
      case "int256":
        encoded += encodeInt256(BigInt(param.value as number));
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
  if (!hex.startsWith("0x")) {
    throw new Error(`decodeHex: missing 0x prefix: "${hex}"`);
  }
  const cleaned = hex.slice(2);
  if (cleaned.length === 0) {
    throw new Error("decodeHex: empty hex value after 0x prefix");
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  // Left-pad to 64 chars (32 bytes) for proper ABI decoding
  const padded = slot.padStart(64, "0");
  const value = BigInt("0x" + padded);
  if (value > MAX_UINT256) {
    throw new Error(`decodeUint256: decoded value exceeds uint256 max`);
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

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
