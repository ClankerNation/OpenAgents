/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
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
    throw new Error("encodeUint256: value out of bounds (must be >= 0 and < 2^256)");
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeInt256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < MIN_INT256 || n > MAX_INT256) {
    throw new Error("encodeInt256: value out of bounds");
  }
  if (n >= 0n) {
    return n.toString(16).padStart(64, "0");
  }
  // Two's complement for negative numbers
  const twosComplement = (1n << 256n) + n;
  return twosComplement.toString(16).padStart(64, "0");
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
    throw new Error("decodeHex: missing 0x prefix");
  }
  return BigInt(hex);
}

export function decodeUint256(slot: string): bigint {
  if (!slot.startsWith("0x")) {
    throw new Error("decodeUint256: missing 0x prefix");
  }
  const padded = "0x" + slot.slice(2).padStart(64, "0");
  return BigInt(padded);
}

export function decodeInt256(slot: string): bigint {
  if (!slot.startsWith("0x")) {
    throw new Error("decodeInt256: missing 0x prefix");
  }
  const padded = "0x" + slot.slice(2).padStart(64, "0");
  const n = BigInt(padded);
  if (n >= (1n << 255n)) {
    return n - (1n << 256n);
  }
  return n;
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
