/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, home C:/Users/55093, working directory F:/jiedan/OpenAgents-bounty-run, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

export type AbiType = "uint256" | "int256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const WORD_HEX_LENGTH = 64;
const UINT256_MAX = (1n << 256n) - 1n;
const INT256_MIN = -(1n << 255n);
const INT256_MAX = (1n << 255n) - 1n;

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > UINT256_MAX) {
    throw new Error("uint256 value out of bounds");
  }
  return n.toString(16).padStart(WORD_HEX_LENGTH, "0");
}

export function encodeInt256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < INT256_MIN || n > INT256_MAX) {
    throw new Error("int256 value out of bounds");
  }
  const encoded = n < 0n ? (1n << 256n) + n : n;
  return encoded.toString(16).padStart(WORD_HEX_LENGTH, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = requireHexPrefix(address, "address");
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error("address must be exactly 20 bytes");
  }
  return cleaned.toLowerCase().padStart(WORD_HEX_LENGTH, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = requireHexPrefix(data, "bytes32");
  if (cleaned.length > WORD_HEX_LENGTH) {
    throw new Error("bytes32 value exceeds 32 bytes");
  }
  return cleaned.toLowerCase().padEnd(WORD_HEX_LENGTH, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(WORD_HEX_LENGTH, "0") : "0".padStart(WORD_HEX_LENGTH, "0");
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
        encoded += hexStr.padEnd(WORD_HEX_LENGTH, "0");
        break;
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  const cleaned = requireHexPrefix(hex, "hex");
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = normalizeWord(slot, "uint256");
  return BigInt("0x" + cleaned);
}

export function decodeInt256(slot: string): bigint {
  const value = decodeUint256(slot);
  return value > INT256_MAX ? value - (1n << 256n) : value;
}

export function decodeAddress(slot: string): string {
  const raw = normalizeWord(slot, "address").slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + normalizeWord(slot, "bool")) !== 0n;
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

function requireHexPrefix(value: string, label: string): string {
  if (!value.startsWith("0x")) {
    throw new Error(`${label} value must have 0x prefix`);
  }
  const cleaned = value.slice(2);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error(`${label} value must be valid hex`);
  }
  return cleaned;
}

function normalizeWord(value: string, label: string): string {
  const cleaned = value.startsWith("0x") ? requireHexPrefix(value, label) : value;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error(`${label} word must be valid hex`);
  }
  if (cleaned.length > WORD_HEX_LENGTH) {
    throw new Error(`${label} word exceeds 32 bytes`);
  }
  return cleaned.padStart(WORD_HEX_LENGTH, "0");
}
