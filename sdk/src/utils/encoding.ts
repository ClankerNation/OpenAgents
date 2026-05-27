/**
 * @contributor-info
 * Name: Karry2019web (Hermes Autonomous Agent)
 * Date: 2026-05-27
 * Session: Autonomous GitHub bounty hunter fixing encoding.ts decodeParameter for dynamic types.
 * Bounty: #198 ($9k)
 * Runtime: Windows 10, Python 3.11 (execute_code sandbox), gh.exe API
 *
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Supports both fixed-size (uint256, address, bytes32, bool) and dynamic types
 * (string, bytes, dynamic arrays).
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

/**
 * Parse slot data into a hex string (left-padded to 64 chars, remove 0x prefix).
 */
function cleanSlot(slot: string): string {
  let cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  if (cleaned.length < 64) {
    cleaned = cleaned.padStart(64, "0");
  } else if (cleaned.length > 64) {
    // Truncate to last 64 hex chars (right-aligned)
    cleaned = cleaned.slice(-64);
  }
  return cleaned;
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  // Overflow check: values > 2^256-1 should throw
  if (n > 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffn) {
    throw new Error("encodeUint256: value exceeds 2^256-1");
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
  // For dynamic types (string, bytes), use ABI encoding v2:
  // head section contains offsets, tail section contains actual data
  let headSize = 0;
  const dynamicIndices: number[] = [];

  for (let i = 0; i < params.length; i++) {
    const t = params[i].type;
    if (t === "string" || t === "bytes") {
      dynamicIndices.push(i);
      headSize += 32; // offset pointer
    } else {
      headSize += 32; // fixed-size slot
    }
  }

  let head = "";
  let tail = "";

  for (let i = 0; i < params.length; i++) {
    const param = params[i];
    switch (param.type) {
      case "uint256":
        head += encodeUint256(BigInt(param.value as number));
        break;
      case "address":
        head += encodeAddress(param.value as string);
        break;
      case "bytes32":
        head += encodeBytes32(param.value as string);
        break;
      case "bool":
        head += encodeBool(param.value as boolean);
        break;
      case "string": {
        const strVal = String(param.value);
        const hexStr = Buffer.from(strVal, "utf-8").toString("hex");
        const dataLen = hexStr.length / 2;
        const padded = hexStr.padEnd(Math.ceil((hexStr.length + 1) / 64) * 64, "0");
        head += encodeUint256(BigInt(headSize + tail.length / 2)); // offset to tail
        tail += encodeUint256(BigInt(dataLen)); // length prefix
        tail += padded;
        break;
      }
      case "bytes": {
        const hexVal = (param.value as string).startsWith("0x")
          ? (param.value as string).slice(2)
          : (param.value as string);
        const dataLen = hexVal.length / 2;
        const padded = hexVal.padEnd(Math.ceil((hexVal.length + 1) / 64) * 64, "0");
        head += encodeUint256(BigInt(headSize + tail.length / 2)); // offset to tail
        tail += encodeUint256(BigInt(dataLen)); // length prefix
        tail += padded;
        break;
      }
    }
  }

  return "0x" + head + tail;
}

export function decodeHex(hex: string): bigint {
  let cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  // Validate: hex string must be valid hex characters
  if (!/^[0-9a-fA-F]+$/.test(cleaned)) {
    throw new Error("decodeHex: invalid hex string (no 0x prefix found)");
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = cleanSlot(slot);
  return BigInt("0x" + cleaned);
}

export function decodeAddress(slot: string): string {
  const raw = cleanSlot(slot).slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + cleanSlot(slot)) !== 0n;
}

/**
 * Decode a parameter from an ABI-encoded hex string at a given offset.
 * Supports fixed types (uint256, address, bool, bytes32) and dynamic types
 * (string, bytes). For dynamic types, reads the offset pointer from the head
 * section, then reads length + data from the tail.
 *
 * @param data - Full ABI-encoded hex string (0x-prefixed)
 * @param type - The ABI type to decode
 * @param offset - Byte offset (0-indexed, each word = 32 bytes) into the data
 * @returns Decoded value as string
 */
export function decodeParameter(data: string, type: string, offset: number): string {
  const raw = data.startsWith("0x") ? data.slice(2) : data;
  
  switch (type) {
    case "uint256": {
      const slot = raw.slice(offset * 64, (offset + 1) * 64);
      return decodeUint256(slot).toString();
    }
    case "address": {
      const slot = raw.slice(offset * 64, (offset + 1) * 64);
      return decodeAddress(slot);
    }
    case "bool": {
      const slot = raw.slice(offset * 64, (offset + 1) * 64);
      return decodeBool(slot).toString();
    }
    case "bytes32": {
      const slot = raw.slice(offset * 64, (offset + 1) * 64);
      return "0x" + slot;
    }
    case "string": {
      // Read offset pointer from head
      const dataOffsetSlot = raw.slice(offset * 64, (offset + 1) * 64);
      const dataOffset = parseInt(decodeUint256(dataOffsetSlot).toString(), 10) * 2; // in hex chars
      // Read length prefix
      const lengthSlot = raw.slice(dataOffset, dataOffset + 64);
      const length = parseInt(decodeUint256(lengthSlot).toString(), 10);
      // Read string data
      const hexStr = raw.slice(dataOffset + 64, dataOffset + 64 + length * 2);
      return Buffer.from(hexStr, "hex").toString("utf-8");
    }
    case "bytes": {
      // Read offset pointer from head
      const dataOffsetSlot = raw.slice(offset * 64, (offset + 1) * 64);
      const dataOffset = parseInt(decodeUint256(dataOffsetSlot).toString(), 10) * 2;
      // Read length prefix
      const lengthSlot = raw.slice(dataOffset, dataOffset + 64);
      const length = parseInt(decodeUint256(lengthSlot).toString(), 10);
      // Read bytes data
      const hexData = raw.slice(dataOffset + 64, dataOffset + 64 + length * 2);
      return "0x" + hexData;
    }
    default:
      throw new Error(`decodeParameter: unsupported type "${type}"`);
  }
}

/**
 * Decode multiple ABI-encoded parameters.
 */
export function decodeParams(data: string, types: string[]): (string | bigint | boolean)[] {
  const results: (string | bigint | boolean)[] = [];
  let offset = 0;
  for (const type of types) {
    const decoded = decodeParameter(data, type, offset);
    if (type === "uint256") {
      results.push(BigInt(decoded));
    } else if (type === "bool") {
      results.push(decoded === "true");
    } else if (type === "bytes32") {
      results.push(decoded);
    } else {
      results.push(decoded);
    }
    if (type === "string" || type === "bytes") {
      offset++; // dynamic type takes one slot in the head
    } else {
      offset++;
    }
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
