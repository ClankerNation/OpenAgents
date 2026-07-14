// @generated-by
// Name: elevasyncsolutions-jpg
// Timestamp: 2026-07-14T21:50:00Z
// Startup configuration: Bounty agent for ClankerNation OpenAgents. Fixing encoding.ts dynamic type handling.
// Runtime: darwin/arm64

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "int256";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const MAX_UINT256 = (1n << 256n) - 1n;

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new Error(`uint256 overflow: value ${n} is out of range [0, 2^256-1]`);
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error(`Invalid address: ${address}`);
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length > 64) {
    throw new Error(`bytes32 too long: expected at most 64 hex chars, got ${cleaned.length}`);
  }
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf-8").toString("hex");
  const length = hex.length / 2;
  const lengthHex = BigInt(length).toString(16).padStart(64, "0");
  const dataHex = hex.padEnd(64 * Math.ceil(hex.length / 64), "0");
  return lengthHex + dataHex;
}

export function encodeBytes(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length % 2 !== 0) {
    throw new Error(`Invalid hex string: odd length ${cleaned.length}`);
  }
  const length = cleaned.length / 2;
  const lengthHex = BigInt(length).toString(16).padStart(64, "0");
  const dataHex = cleaned.padEnd(64 * Math.ceil(cleaned.length / 64), "0");
  return lengthHex + dataHex;
}

export function encodeParams(params: AbiParam[]): string {
  let staticPart = "";
  const dynamicParts: string[] = [];

  for (const param of params) {
    switch (param.type) {
      case "uint256":
        staticPart += encodeUint256(BigInt(param.value as number));
        break;
      case "address":
        staticPart += encodeAddress(param.value as string);
        break;
      case "bytes32":
        staticPart += encodeBytes32(param.value as string);
        break;
      case "bool":
        staticPart += encodeBool(param.value as boolean);
        break;
      case "string":
        dynamicParts.push(encodeString(param.value as string));
        break;
      case "bytes":
        dynamicParts.push(encodeBytes(param.value as string));
        break;
      default:
        throw new Error(`Unsupported type: ${param.type}`);
    }
  }

  if (dynamicParts.length > 0) {
    const headSize = params.length * 32;
    let offset = headSize;
    for (const dp of dynamicParts) {
      staticPart += BigInt(offset).toString(16).padStart(64, "0");
      offset += dp.length / 2;
    }
  }

  const allDynamic = dynamicParts.join("");
  return "0x" + staticPart + allDynamic;
}

export function decodeHex(hex: string): bigint {
  if (typeof hex !== "string") {
    throw new Error(`Invalid hex input: expected string, got ${typeof hex}`);
  }
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error(`Invalid hex string: ${hex}`);
  }
  if (cleaned === "") return 0n;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const raw = cleaned.slice(-40).padStart(40, "0");
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  const padded = slot.padStart(64, "0");
  return BigInt("0x" + padded) !== 0n;
}

export function decodeString(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const length = Number(BigInt("0x" + cleaned.slice(0, 64)));
  const strHex = cleaned.slice(64, 64 + length * 2);
  return Buffer.from(strHex, "hex").toString("utf-8");
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
