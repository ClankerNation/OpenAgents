/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-25
 * @fixes #198 — Add dynamic type decoding (string, bytes, dynamic array, tuple)
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "uint[]" | "string[]" | "address[]";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | string[] | boolean[] | number[] | bigint[];
}

export interface DecodedValue {
  type: string;
  value: unknown;
}

/**
 * Decode a single ABI-encoded 32-byte slot to its native JS value.
 * Handles fixed-size types (uint256, address, bool, bytes32).
 */
export function decodeSlot(slot: string): unknown {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;

  // Address (last 20 bytes of slot)
  if (cleaned.length === 64) {
    const addr = "0x" + cleaned.slice(-40).toLowerCase();
    return addr;
  }

  // Bool
  const num = BigInt("0x" + cleaned);
  if (num === 0n || num === 1n) {
    return Boolean(num);
  }

  // uint256
  return num;
}

/**
 * Decode a dynamic type (string, bytes, dynamic array) from an ABI-encoded hex string.
 * Dynamic types are encoded as: offset (32 bytes) + length (32 bytes) + data.
 * For strings/bytes: reads length, then extracts UTF-8 / raw bytes.
 * For arrays: reads length, then iterates elements starting at offset+0x40.
 */
export function decodeDynamicType(hex: string, type: string): unknown {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;

  // Dynamic array: [offset][length][elem0][elem1]...
  if (type.endsWith("[]")) {
    const elemType = type.slice(0, -2); // e.g. "uint256", "address", "string"
    const offset = BigInt("0x" + cleaned.slice(0, 64));
    const length = BigInt("0x" + cleaned.slice(64, 128));

    if (length === 0n) return [];

    const baseOffset = Number(offset);
    const elements: unknown[] = [];

    for (let i = 0; i < Number(length); i++) {
      const pos = baseOffset + i * 64;
      const elemHex = cleaned.slice(pos, pos + 64);

      if (elemType === "string" || elemType === "bytes") {
        // Element is a dynamic type: [offset][data]
        const elemOffset = BigInt("0x" + elemHex.slice(0, 64));
        const elemDataHex = cleaned.slice(Number(elemOffset) * 2);
        if (elemType === "string") {
          const elemLen = BigInt("0x" + elemDataHex.slice(0, 64));
          const dataHex = elemDataHex.slice(64, 64 + Number(elemLen) * 2);
          elements.push(hexToString(dataHex));
        } else {
          const elemLen = BigInt("0x" + elemDataHex.slice(0, 64));
          const dataHex = elemDataHex.slice(64, 64 + Number(elemLen) * 2);
          elements.push(hexToBytes(dataHex));
        }
      } else {
        // Fixed-size element
        elements.push(decodeSlot("0x" + elemHex));
      }
    }

    return elements;
  }

  // String: [offset][length][utf8 bytes]
  if (type === "string") {
    const length = BigInt("0x" + cleaned.slice(0, 64));
    const dataHex = cleaned.slice(64, 64 + Number(length) * 2);
    return hexToString(dataHex);
  }

  // Bytes: [offset][length][raw bytes]
  if (type === "bytes") {
    const length = BigInt("0x" + cleaned.slice(0, 64));
    const dataHex = cleaned.slice(64, 64 + Number(length) * 2);
    return hexToBytes(dataHex);
  }

  return cleaned;
}

/**
 * Decode a hex string to a JavaScript string (UTF-8).
 */
export function hexToString(hex: string): string {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  let str = "";
  for (let i = 0; i < cleaned.length; i += 2) {
    const byte = parseInt(cleaned.slice(i, i + 2), 16);
    // Handle UTF-8 multi-byte sequences
    if (byte >= 0xF0) {
      const c1 = parseInt(cleaned.slice(i, i + 2), 16);
      const c2 = parseInt(cleaned.slice(i + 2, i + 4), 16);
      const c3 = parseInt(cleaned.slice(i + 4, i + 6), 16);
      const c4 = parseInt(cleaned.slice(i + 6, i + 8), 16);
      const codePoint = ((c1 & 0x07) << 18) | ((c2 & 0x3F) << 12) | ((c3 & 0x3F) << 6) | (c4 & 0x3F);
      str += String.fromCodePoint(codePoint);
      i += 6;
    } else if (byte >= 0xC0) {
      const c2 = parseInt(cleaned.slice(i + 2, i + 4), 16);
      const codePoint = ((byte & 0x1F) << 6) | (c2 & 0x3F);
      str += String.fromCodePoint(codePoint);
      i += 2;
    } else {
      str += String.fromCharCode(byte);
    }
  }
  return str;
}

/**
 * Decode a hex string to a Uint8Array.
 */
export function hexToBytes(hex: string): Uint8Array {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  const bytes = new Uint8Array(cleaned.length / 2);
  for (let i = 0; i < cleaned.length; i += 2) {
    bytes[i / 2] = parseInt(cleaned.slice(i, i + 2), 16);
  }
  return bytes;
}

/**
 * Encode a dynamic type (string, bytes, array) to ABI hex format.
 */
export function encodeDynamicType(value: unknown, type: string): string {
  if (Array.isArray(value)) {
    const elemType = type.slice(0, -2);
    let hex = "";

    // First, encode all elements (tail)
    const tailHexes: string[] = [];
    for (const elem of value) {
      if (elemType === "string" || elemType === "bytes") {
        const encoded = typeof elem === "string"
          ? encodeDynamicType(elem, elemType)
          : "";
        tailHexes.push(encoded);
      } else if (typeof elem === "string" && elem.startsWith("0x")) {
        tailHexes.push(elem.slice(2).padStart(64, "0"));
      } else {
        tailHexes.push(encodeUint256(BigInt(elem as number | bigint)).padStart(64, "0"));
      }
    }

    // Head: offset + lengths + values
    const dataOffset = 32 * (1 + value.length + tailHexes.length); // offset + len + tail slots
    let head = dataOffset.toString(16).padStart(64, "0"); // offset to tail
    head += value.length.toString(16).padStart(64, "0"); // array length

    for (let i = 0; i < value.length; i++) {
      if (elemType === "string" || elemType === "bytes") {
        const elemVal = value[i] as string;
        const rawBytes = elemType === "string"
          ? Buffer.from(elemVal, "utf-8")
          : Buffer.from((elemVal as string).startsWith("0x") ? (elemVal as string).slice(2) : elemVal, "hex");
        const elemOff = dataOffset + i * 64;
        head += elemOff.toString(16).padStart(64, "0"); // offset to this element
      } else {
        const encoded = encodeUint256(BigInt(value[i] as number | bigint)).padStart(64, "0");
        head += encoded;
      }
    }

    // Tail: actual element data
    for (const tail of tailHexes) {
      head += tail;
    }

    return "0x" + head;
  }

  if (type === "string") {
    const raw = Buffer.from(value as string, "utf-8");
    const len = raw.length.toString(16).padStart(64, "0");
    const data = raw.toString("hex").padEnd(64, "0");
    return "0x" + len + data;
  }

  if (type === "bytes") {
    const hexStr = (value as string).startsWith("0x")
      ? (value as string).slice(2)
      : (value as string);
    const raw = Buffer.from(hexStr, "hex");
    const len = raw.length.toString(16).padStart(64, "0");
    const data = raw.toString("hex").padEnd(64, "0");
    return "0x" + len + data;
  }

  return "0x" + value;
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n >= 2n ** 256n) {
    throw new Error(`uint256 overflow: ${n}`);
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
        encoded += encodeDynamicType(param.value as string, "string");
        break;
      case "bytes":
        encoded += encodeDynamicType(param.value as string, "bytes");
        break;
      case "uint[]":
      case "string[]":
      case "address[]":
        encoded += encodeDynamicType(param.value, param.type);
        break;
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  if (!hex.startsWith("0x")) {
    throw new Error(`decodeHex requires "0x" prefix, got: ${hex}`);
  }
  const cleaned = hex.slice(2);
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned.padStart(64, "0"));
}

export function decodeAddress(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const raw = cleaned.padStart(64, "0").slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned.padStart(64, "0")) !== 0n;
}

export function decodeParam(hex: string, type: string): DecodedValue {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;

  if (type === "string" || type === "bytes") {
    return { type, value: decodeDynamicType(cleaned, type) };
  }

  if (type.endsWith("[]")) {
    return { type, value: decodeDynamicType(cleaned, type) };
  }

  return { type, value: decodeSlot("0x" + cleaned) };
}

export function decodeTuple(hexes: string[], types: string[]): DecodedValue[] {
  return hexes.map((hex, i) => decodeParam(hex, types[i]));
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
