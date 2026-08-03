/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
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

export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf8").toString("hex");
  const len = hex.length / 2;
  const lenHex = BigInt(len).toString(16).padStart(64, "0");
  const padded = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return lenHex + padded;
}

export function encodeDynamicBytes(data: Uint8Array | string): string {
  const hex = typeof data === "string"
    ? (data.startsWith("0x") ? data.slice(2) : Buffer.from(data, "utf8").toString("hex"))
    : Buffer.from(data).toString("hex");
  const len = hex.length / 2;
  const lenHex = BigInt(len).toString(16).padStart(64, "0");
  const padded = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return lenHex + padded;
}

export function encodeParams(params: AbiParam[]): string {
  let staticPart = "";
  let dynamicPart = "";
  const offsets: number[] = [];
  let currentOffset = params.length * 32;

  for (const param of params) {
    if (param.type === "string" || param.type === "bytes") {
      offsets.push(currentOffset);
      const encoded = param.type === "string"
        ? encodeString(param.value as string)
        : encodeDynamicBytes(param.value as string);
      currentOffset += encoded.length / 2;
      dynamicPart += encoded;
    } else {
      offsets.push(-1);
    }
  }

  let idx = 0;
  for (const param of params) {
    if (param.type === "string" || param.type === "bytes") {
      staticPart += BigInt(offsets[idx]).toString(16).padStart(64, "0");
    } else {
      switch (param.type) {
        case "uint256": staticPart += encodeUint256(BigInt(param.value as number)); break;
        case "address": staticPart += encodeAddress(param.value as string); break;
        case "bytes32": staticPart += encodeBytes32(param.value as string); break;
        case "bool": staticPart += encodeBool(param.value as boolean); break;
      }
    }
    idx++;
  }

  return "0x" + staticPart + dynamicPart;
}

export function decodeHex(hex: string): bigint {
  if (typeof hex !== "string") throw new Error("decodeHex: expected string");
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) throw new Error("decodeHex: invalid hex");
  return BigInt("0x" + (cleaned || "0"));
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
  return BigInt("0x" + slot) !== 0n;
}

/**
 * Decode a single ABI-encoded parameter.
 * Handles static types (uint256, address, bytes32, bool) and dynamic types
 * (string, bytes, dynamic arrays via offset-based pointers).
 */
export function decodeParameter(
  type: string,
  data: string
): bigint | string | Uint8Array | boolean {
  const hex = data.startsWith("0x") ? data.slice(2) : data;

  if (type === "uint256") return decodeUint256("0x" + hex.slice(0, 64));
  if (type === "address") return decodeAddress(hex.slice(0, 64));
  if (type === "bytes32") return "0x" + hex.slice(0, 64);
  if (type === "bool") return decodeBool(hex.slice(0, 64));

  // Dynamic types: first 32 bytes = offset
  if (type === "string") {
    const offset = Number(decodeUint256("0x" + hex.slice(0, 64))) * 2;
    const len = Number(decodeUint256("0x" + hex.slice(offset, offset + 64)));
    const strHex = hex.slice(offset + 64, offset + 64 + len * 2);
    return Buffer.from(strHex, "hex").toString("utf8");
  }

  if (type === "bytes") {
    const offset = Number(decodeUint256("0x" + hex.slice(0, 64))) * 2;
    const len = Number(decodeUint256("0x" + hex.slice(offset, offset + 64)));
    const bytesHex = hex.slice(offset + 64, offset + 64 + len * 2);
    return new Uint8Array(Buffer.from(bytesHex, "hex"));
  }

  // Dynamic array
  const arrMatch = type.match(/^(.+)\[\]$/);
  if (arrMatch) {
    const elemType = arrMatch[1];
    const offset = Number(decodeUint256("0x" + hex.slice(0, 64))) * 2;
    const arrLen = Number(decodeUint256("0x" + hex.slice(offset, offset + 64)));
    const results: (bigint | string | boolean)[] = [];
    for (let i = 0; i < arrLen; i++) {
      const es = offset + 64 + i * 64;
      results.push(decodeParameter(elemType, "0x" + hex.slice(es, es + 64)) as bigint | string | boolean);
    }
    return results as unknown as Uint8Array;
  }

  throw new Error('decodeParameter: unsupported type "' + type + '"');
}

/**
 * Decode multiple ABI-encoded parameters.
 */
export function decodeParams(
  types: string[],
  data: string
): (bigint | string | Uint8Array | boolean)[] {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const results: (bigint | string | Uint8Array | boolean)[] = [];

  for (let i = 0; i < types.length; i++) {
    const type = types[i];
    const slotStart = i * 64;

    if (type === "uint256") results.push(decodeUint256("0x" + hex.slice(slotStart, slotStart + 64)));
    else if (type === "address") results.push(decodeAddress(hex.slice(slotStart, slotStart + 64)));
    else if (type === "bytes32") results.push("0x" + hex.slice(slotStart, slotStart + 64));
    else if (type === "bool") results.push(decodeBool(hex.slice(slotStart, slotStart + 64)));
    else results.push(decodeParameter(type, "0x" + hex.slice(slotStart)));
  }

  return results;
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
