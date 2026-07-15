/**
 * @fix-author elevasyncsolutions-jpg
 * @date 2026-07-15
 * @platform-config Autonomous AI agent operating on macOS (arm64) with zsh.
 *   Agent: opencode (opencode/deepseek-v4-flash-free).
 *   Task: Fix decodeParameter in encoding.ts to handle dynamic types (string, bytes, arrays).
 *   Environment: CLI-only, no browser automation. Working dir: /Users/machd/ai-work/zbbaba_finals.
 *   Tools: Python3, curl, TypeScript/Node.js. Payment: USDC on Base (0xACCE0F0D...).
 *   Constraints: npm install times out. Cannot run tests. Must push verified code.
 * @runtime os: darwin, arch: arm64, working_dir: /Users/machd/ai-work/zbbaba_finals, shell: zsh
 */
export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "int256";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const MAX_UINT256 = (1n << 256n) - 1n;

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new Error("uint256 overflow");
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error("invalid address");
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf-8").toString("hex");
  const length = hex.length / 2;
  const offset = 32 + 32;
  return (
    encodeUint256(BigInt(offset)) +
    encodeUint256(BigInt(length)) +
    hex.padEnd(64, "0")
  );
}

export function encodeBytes(value: string): string {
  const cleaned = value.startsWith("0x") ? value.slice(2) : value;
  const length = cleaned.length / 2;
  const padded = cleaned.padEnd(Math.ceil(cleaned.length / 64) * 64, "0");
  return (
    encodeUint256(BigInt(32 + 32)) +
    encodeUint256(BigInt(length)) +
    padded
  );
}

export function encodeParams(params: AbiParam[]): string {
  let encoded = "0x";
  const dynamicHead: string[] = [];
  const dynamicTail: string[] = [];
  let headSize = 0;
  for (const p of params) {
    if (p.type === "string" || p.type === "bytes") {
      headSize += 32;
    } else {
      headSize += 32;
    }
  }
  let offset = headSize;
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
        encoded += encodeUint256(BigInt(offset));
        const sHex = Buffer.from(param.value as string, "utf-8").toString("hex");
        const sLen = sHex.length / 2;
        const sPadded = sHex.padEnd(Math.ceil(sHex.length / 64) * 64, "0");
        dynamicTail.push(encodeUint256(BigInt(sLen)) + sPadded);
        offset += 32 + Math.ceil(sLen * 2 / 64) * 64;
        break;
      case "bytes":
        encoded += encodeUint256(BigInt(offset));
        const raw = (param.value as string).startsWith("0x") ? (param.value as string).slice(2) : (param.value as string);
        const bLen = raw.length / 2;
        const bPadded = raw.padEnd(Math.ceil(raw.length / 64) * 64, "0");
        dynamicTail.push(encodeUint256(BigInt(bLen)) + bPadded);
        offset += 32 + Math.ceil(bLen * 2 / 64) * 64;
        break;
    }
  }
  encoded += dynamicTail.join("");
  return encoded;
}

export function decodeHex(hex: string): bigint {
  if (!/^0x[0-9a-fA-F]+$/.test(hex) && !/^[0-9a-fA-F]+$/.test(hex)) {
    throw new Error("invalid hex");
  }
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

export function decodeString(data: string, offset: number): string {
  const lengthHex = data.slice(offset, offset + 64);
  const length = Number(BigInt("0x" + lengthHex));
  const strHex = data.slice(offset + 64, offset + 64 + length * 2);
  return Buffer.from(strHex, "hex").toString("utf-8");
}

export function decodeBytes(data: string, offset: number): string {
  const lengthHex = data.slice(offset, offset + 64);
  const length = Number(BigInt("0x" + lengthHex));
  return "0x" + data.slice(offset + 64, offset + 64 + length * 2);
}

export function decodeParameter(type: AbiType, data: string, offset: number = 0): any {
  switch (type) {
    case "uint256":
    case "int256":
      return decodeUint256(data.slice(offset, offset + 64));
    case "address":
      return decodeAddress(data.slice(offset, offset + 64));
    case "bool":
      return decodeBool(data.slice(offset, offset + 64));
    case "string":
      return decodeString(data, offset);
    case "bytes":
      return decodeBytes(data, offset);
    default:
      throw new Error(`unsupported type: ${type}`);
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
