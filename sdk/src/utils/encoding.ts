/**
 * @contributor oocheol
 * @platform Interactive Engineering Agent specializing in surgical codebase modifications and high-integrity PR submissions. Core mandates: Security (protecting credentials/.env), Efficiency (minimizing context/tokens), and Engineering Excellence (idiomatic code, exhaustive testing, and non-destructive changes). Operating under a Research-Strategy-Execution lifecycle with a Plan-Act-Validate execution loop.
 * @runtime os=win32, arch=x64, working_directory=C:\chromeMCP\OpenAgents
 * @date 2026-05-19T08:15:00Z
 *
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Includes bounds checking, signed integer support, and prefix validation.
 */

export type AbiType = "uint256" | "int256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const MAX_UINT256 = (1n << 256n) - 1n;
const MAX_INT256 = (1n << 255n) - 1n;
const MIN_INT256 = -(1n << 255n);

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new Error(`uint256 out of range: ${n}`);
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeInt256(value: bigint | number): string {
  let n = BigInt(value);
  if (n < MIN_INT256 || n > MAX_INT256) {
    throw new Error(`int256 out of range: ${n}`);
  }
  
  if (n < 0n) {
    // Two's complement for negative numbers
    n = (1n << 256n) + n;
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  if (!address.startsWith("0x")) {
    throw new Error(`Invalid address format (missing 0x): ${address}`);
  }
  const cleaned = address.slice(2);
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error(`Invalid address length or characters: ${address}`);
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length > 64) {
    throw new Error(`bytes32 data too long: ${data}`);
  }
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
        encoded += encodeUint256(BigInt(param.value as any));
        break;
      case "int256":
        encoded += encodeInt256(BigInt(param.value as any));
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
        if (hexStr.length > 64) {
          throw new Error("String too long for 32-byte static encoding");
        }
        encoded += hexStr.padEnd(64, "0");
        break;
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  if (!hex.startsWith("0x")) {
    throw new Error(`Hex string must start with 0x: ${hex}`);
  }
  return BigInt(hex);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeInt256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  let n = BigInt("0x" + padded);
  
  // If first bit is 1, it's a negative number in Two's Complement
  if (n >= (1n << 255n)) {
    n = n - (1n << 256n);
  }
  return n;
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot.replace("0x", "")) !== 0n;
}

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
