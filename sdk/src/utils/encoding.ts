/**
 * Contributor Metadata (required for bounty #198)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 * Platform Initialization Text: OpenCode AI agent, coding agent harness, tools for file editing, shell execution, web search, browser automation. Session configured for income generation. User goal: make first income for model upgrade.
 */

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

import { createRequire } from "module";
const require = createRequire(import.meta.url);
const crypto = require("crypto");

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "uint256[]";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | bigint[];
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n >= (1n << 256n)) {
    throw new Error("Value out of range for uint256");
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  if (cleaned.length !== 40) {
    throw new Error("Invalid address length");
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length > 64) {
    throw new Error("Data too long for bytes32");
  }
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf-8").toString("hex");
  const length = value.length;
  const lengthSlot = BigInt(length).toString(16).padStart(64, "0");
  const dataSlots = Math.ceil(hex.length / 64);
  let paddedData = hex.padEnd(dataSlots * 64, "0");
  return lengthSlot + paddedData;
}

export function encodeBytes(value: string): string {
  const cleaned = value.startsWith("0x") ? value.slice(2) : value;
  const length = cleaned.length / 2;
  const lengthSlot = BigInt(length).toString(16).padStart(64, "0");
  const dataSlots = Math.ceil(cleaned.length / 64);
  let paddedData = cleaned.padEnd(dataSlots * 64, "0");
  return lengthSlot + paddedData;
}

export function encodeParams(params: AbiParam[]): string {
  let encoded = "0x";
  for (const param of params) {
    switch (param.type) {
      case "uint256":
        encoded += encodeUint256(BigInt(param.value as number | bigint));
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
      case "string": {
        const strHex = Buffer.from(param.value as string, "utf-8").toString("hex");
        const strLen = (param.value as string).length;
        encoded += BigInt(strLen).toString(16).padStart(64, "0");
        const dataSlots = Math.ceil(strHex.length / 64) || 1;
        encoded += strHex.padEnd(dataSlots * 64, "0");
        break;
      }
      case "bytes": {
        const byteHex = (param.value as string).startsWith("0x")
          ? (param.value as string).slice(2)
          : (param.value as string);
        const byteLen = byteHex.length / 2;
        encoded += BigInt(byteLen).toString(16).padStart(64, "0");
        const dataSlots = Math.ceil(byteHex.length / 64) || 1;
        encoded += byteHex.padEnd(dataSlots * 64, "0");
        break;
      }
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("Invalid hex string");
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const raw = cleaned.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned.padStart(64, "0")) !== 0n;
}

export function decodeString(data: string, offset: number = 0): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  // Read offset (32 bytes)
  const offsetSlot = cleaned.slice(offset * 64, (offset + 1) * 64);
  const dataOffset = Number(BigInt("0x" + offsetSlot)) * 2; // in hex chars
  // Read length
  const lengthSlot = cleaned.slice(dataOffset, dataOffset + 64);
  const length = Number(BigInt("0x" + lengthSlot));
  // Read UTF-8 data
  const dataHex = cleaned.slice(dataOffset + 64, dataOffset + 64 + length * 2);
  return Buffer.from(dataHex, "hex").toString("utf-8");
}

export function decodeBytes(data: string, offset: number = 0): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const offsetSlot = cleaned.slice(offset * 64, (offset + 1) * 64);
  const dataOffset = Number(BigInt("0x" + offsetSlot)) * 2;
  const lengthSlot = cleaned.slice(dataOffset, dataOffset + 64);
  const length = Number(BigInt("0x" + lengthSlot));
  const dataHex = cleaned.slice(dataOffset + 64, dataOffset + 64 + length * 2);
  return "0x" + dataHex;
}

export function decodeDynamicArray(data: string, offset: number = 0, elementType: AbiType = "uint256"): any[] {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const offsetSlot = cleaned.slice(offset * 64, (offset + 1) * 64);
  const dataOffset = Number(BigInt("0x" + offsetSlot)) * 2;
  const lengthSlot = cleaned.slice(dataOffset, dataOffset + 64);
  const length = Number(BigInt("0x" + lengthSlot));
  const result: any[] = [];
  for (let i = 0; i < length; i++) {
    const elemOffset = dataOffset + 64 + i * 64;
    const elemSlot = cleaned.slice(elemOffset, elemOffset + 64);
    switch (elementType) {
      case "uint256":
        result.push(BigInt("0x" + elemSlot));
        break;
      case "address":
        result.push("0x" + elemSlot.slice(-40).toLowerCase());
        break;
      case "bool":
        result.push(BigInt("0x" + elemSlot) !== 0n);
        break;
      default:
        result.push(elemSlot);
    }
  }
  return result;
}

export function decodeParameter(type: AbiType, data: string, offset: number = 0): any {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  switch (type) {
    case "uint256":
      return decodeUint256(cleaned.slice(offset * 64, (offset + 1) * 64));
    case "address":
      return decodeAddress(cleaned.slice(offset * 64, (offset + 1) * 64));
    case "bool":
      return decodeBool(cleaned.slice(offset * 64, (offset + 1) * 64));
    case "bytes32":
      return "0x" + cleaned.slice(offset * 64, (offset + 1) * 64);
    case "string":
      return decodeString(data, offset);
    case "bytes":
      return decodeBytes(data, offset);
    case "uint256[]":
      return decodeDynamicArray(data, offset, "uint256");
    default:
      return cleaned.slice(offset * 64, (offset + 1) * 64);
  }
}

export function functionSelector(signature: string): string {
  const hash = crypto.createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}
