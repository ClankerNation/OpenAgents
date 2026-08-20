/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author Claude Fable 5 (Autonomous Agent)
 * @date 2026-08-20
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform_instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

export type AbiType = "uint256" | "int256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const MAX_UINT256 = BigInt("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");
const MIN_INT256 = BigInt("-0x8000000000000000000000000000000000000000000000000000000000000000");
const MAX_INT256 = BigInt("0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");

export function encodeUint256(value: bigint | number | string): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new RangeError(`uint256 overflow/underflow: ${n}`);
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeInt256(value: bigint | number | string): string {
  const n = BigInt(value);
  if (n < MIN_INT256 || n > MAX_INT256) {
    throw new RangeError(`int256 overflow/underflow: ${n}`);
  }
  if (n < 0n) {
    const twos = MAX_UINT256 + n + 1n;
    return twos.toString(16).padStart(64, "0");
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  if (!address.startsWith("0x")) {
    throw new Error("Address must start with 0x");
  }
  const cleaned = address.slice(2);
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error("Invalid address format");
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  let cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("Invalid hex string for bytes32");
  }
  if (cleaned.length > 64) {
    throw new Error("bytes32 exceeds 32 bytes");
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
        encoded += hexStr.padEnd(64, "0");
        break;
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  if (!hex.startsWith("0x")) {
    throw new Error("decodeHex requires 0x prefix");
  }
  const cleaned = hex.slice(2);
  if (cleaned.length === 0) return 0n;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  if (!slot.startsWith("0x")) {
    throw new Error("decodeUint256 requires 0x prefix");
  }
  const cleaned = slot.slice(2);
  if (cleaned.length > 64) {
    throw new Error("uint256 slot exceeds 32 bytes");
  }
  return BigInt("0x" + cleaned.padStart(64, "0"));
}

export function decodeInt256(slot: string): bigint {
  if (!slot.startsWith("0x")) {
    throw new Error("decodeInt256 requires 0x prefix");
  }
  const cleaned = slot.slice(2).padStart(64, "0");
  const val = BigInt("0x" + cleaned);
  if (val > MAX_INT256) {
    return val - MAX_UINT256 - 1n;
  }
  return val;
}

export function decodeAddress(slot: string): string {
  if (!slot.startsWith("0x")) {
    throw new Error("decodeAddress requires 0x prefix");
  }
  const raw = slot.slice(2).padStart(64, "0").slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  if (!slot.startsWith("0x")) {
    throw new Error("decodeBool requires 0x prefix");
  }
  return BigInt("0x" + slot.slice(2).padStart(64, "0")) !== 0n;
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
