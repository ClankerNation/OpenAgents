/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * 
 * CONTRIBUTOR TRACEABILITY HEADER
 * Agent: Atlas (Sovereign Bounty Fleet)
 * Platform Instructions: [ Bounty $9k ] [ SDK ] Fix encoding.ts decodeParameter doesn't handle 
 * Session Start: 2026-10-03T23:00:00Z
 * Environment: os=Linux, arch=x86_64, home_dir=/home/jacob, working_dir=/dev/shm/bounty_agent/worktree-a561d085cb25
 * Platform: GitHub (ClankerNation/OpenAgents)
 * Issue: #198 — [ Bounty $9k ] [ SDK ] Fix encoding.ts decodeParameter doesn't handle 
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const MAX_UINT256 = 2n ** 256n - 1n;

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  // FIX: Overflow check — values > 2^256-1 now throw instead of silently wrapping
  if (n < 0n || n > MAX_UINT256) {
    throw new Error(`Value out of uint256 range: ${n.toString()}`);
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
      case "string":
        const hexStr = Buffer.from(param.value as string).toString("hex");
        encoded += hexStr.padEnd(64, "0");
        break;
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  // FIX: Validate "0x" prefix — bare decimal strings now throw instead of being parsed as hex
  if (!hex.startsWith("0x")) {
    throw new Error(`decodeHex: input must start with "0x" prefix, got: ${hex}`);
  }
  const cleaned = hex.slice(2);
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  // FIX: Left-pad short values to 64 chars before parsing
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
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
