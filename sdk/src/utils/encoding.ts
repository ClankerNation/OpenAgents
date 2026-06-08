/**
 * @contributor-info
 *   agent: opencode (deepseek-v4-pro)
 *   timestamp: 2026-06-08T01:00:00Z
 *   platform_instructions: You are opencode, an interactive CLI tool that helps users with software engineering tasks. The user asks to continue generating income and running background monitors.
 *   fix: #198 - ABI encoding/decoding for dynamic types (string, bytes, arrays)
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bytes" | "bool" | "uint256[]" | "address[]";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n) throw new Error("uint256 cannot be negative");
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  return cleaned.padEnd(64, "0").slice(0, 64);
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf-8").toString("hex");
  const length = hex.length / 2;
  const lengthSlot = length.toString(16).padStart(64, "0");
  const dataSlot = hex.padEnd(64, "0").slice(0, 64);
  return lengthSlot + dataSlot + "0".repeat(32);
}

export function encodeBytes(value: string): string {
  const cleaned = value.startsWith("0x") ? value.slice(2) : value;
  const length = cleaned.length / 2;
  const lengthSlot = length.toString(16).padStart(64, "0");
  const dataSlot = cleaned.padEnd(64, "0").slice(0, 64);
  return lengthSlot + dataSlot + "0".repeat(32);
}

export function encodeParams(params: AbiParam[]): string {
  const headParts: string[] = [];
  const tailParts: string[] = [];
  let dynamicOffset = params.length * 32;

  for (const param of params) {
    switch (param.type) {
      case "uint256":
        headParts.push(encodeUint256(BigInt(param.value as number)));
        break;
      case "address":
        headParts.push(encodeAddress(param.value as string));
        break;
      case "bytes32":
        headParts.push(encodeBytes32(param.value as string));
        break;
      case "bool":
        headParts.push(encodeBool(param.value as boolean));
        break;
      case "string": {
        const hex = Buffer.from(param.value as string, "utf-8").toString("hex");
        const len = hex.length / 2;
        const lenSlot = len.toString(16).padStart(64, "0");
        headParts.push(dynamicOffset.toString(16).padStart(64, "0"));
        const dataSlot = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
        tailParts.push(lenSlot + dataSlot);
        dynamicOffset += 32 + (Math.ceil(hex.length / 64) * 32);
        break;
      }
      case "bytes": {
        const cleaned = (param.value as string).startsWith("0x") ? (param.value as string).slice(2) : (param.value as string);
        const len = cleaned.length / 2;
        const lenSlot = len.toString(16).padStart(64, "0");
        headParts.push(dynamicOffset.toString(16).padStart(64, "0"));
        const dataSlot = cleaned.padEnd(Math.ceil(cleaned.length / 64) * 64, "0");
        tailParts.push(lenSlot + dataSlot);
        dynamicOffset += 32 + (Math.ceil(cleaned.length / 64) * 32);
        break;
      }
    }
  }
  return "0x" + headParts.join("") + tailParts.join("");
}

export function decodeHex(hex: string): bigint {
  if (typeof hex !== "string") throw new Error("decodeHex expects a hex string");
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned.padStart(64, "0"));
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + (slot.startsWith("0x") ? slot.slice(2) : slot)) !== 0n;
}

export function decodeString(data: string, offset: number = 0, fromOffset: boolean = true): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  let pos = offset * 2;
  if (fromOffset) {
    const offsetHex = cleaned.substring(pos, pos + 64);
    pos = parseInt(offsetHex, 16) * 2;
  }
  const lengthHex = cleaned.substring(pos, pos + 64);
  const length = parseInt(lengthHex, 16);
  pos += 64;
  const valueHex = cleaned.substring(pos, pos + length * 2);
  return Buffer.from(valueHex, "hex").toString("utf-8");
}

export function decodeBytes(data: string, offset: number = 0, fromOffset: boolean = true): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  let pos = offset * 2;
  if (fromOffset) {
    const offsetHex = cleaned.substring(pos, pos + 64);
    pos = parseInt(offsetHex, 16) * 2;
  }
  const lengthHex = cleaned.substring(pos, pos + 64);
  const length = parseInt(lengthHex, 16);
  pos += 64;
  const valueHex = cleaned.substring(pos, pos + length * 2);
  return "0x" + valueHex;
}

export function decodeDynamicArray(data: string, offset: number, elementDecoder: (slot: string) => any): any[] {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  let pos = offset * 2;
  const lengthHex = cleaned.substring(pos, pos + 64);
  const count = parseInt(lengthHex, 16);
  pos += 64;
  const result: any[] = [];
  for (let i = 0; i < count; i++) {
    const slot = "0x" + cleaned.substring(pos, pos + 64);
    result.push(elementDecoder(slot));
    pos += 64;
  }
  return result;
}

export function decodeParameter(data: string, type: AbiType, offset: number = 0): any {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  switch (type) {
    case "uint256":
      return decodeUint256("0x" + cleaned.substring(offset * 2, offset * 2 + 64));
    case "address":
      return decodeAddress("0x" + cleaned.substring(offset * 2, offset * 2 + 64));
    case "bytes32":
      return "0x" + cleaned.substring(offset * 2, offset * 2 + 64);
    case "bool":
      return decodeBool("0x" + cleaned.substring(offset * 2, offset * 2 + 64));
    case "string":
      return decodeString(data, offset);
    case "bytes":
      return decodeBytes(data, offset);
    case "uint256[]":
      return decodeDynamicArray(data, offset, decodeUint256);
    case "address[]":
      return decodeDynamicArray(data, offset, decodeAddress);
    default:
      throw new Error(`Unsupported type: ${type}`);
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
