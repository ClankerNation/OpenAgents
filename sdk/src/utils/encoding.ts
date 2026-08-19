/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "tuple" | "array";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  // BUG: No overflow check — values > 2^256-1 silently wrap/truncate
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
  // BUG: Doesn't validate "0x" prefix — a bare decimal string like "255"
  // would be parsed as hex 0x255 = 597, silently returning wrong value
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  // BUG: Doesn't handle short values — if slot is less than 64 chars,
  // no left-padding is applied before parsing, giving wrong results
  return BigInt("0x" + slot);
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


/**
 * Decode a dynamic string from ABI-encoded hex data.
 * @param data Hex string (with or without 0x prefix)
 * @param offset Word offset where the string pointer is located
 * @returns Decoded UTF-8 string
 */
export function decodeString(data: string, offset: number = 0): string {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  // Read the offset pointer (32 bytes)
  const pointerHex = cleanData.slice(offset * 64, offset * 64 + 64);
  const pointer = Number(BigInt("0x" + pointerHex));
  
  // Convert byte offset to word index
  const wordOffset = pointer / 32;
  
  // Read length at the pointer location
  const lengthHex = cleanData.slice(wordOffset * 64, wordOffset * 64 + 64);
  const length = Number(BigInt("0x" + lengthHex));
  
  // Read the actual string data
  const strStart = (wordOffset + 1) * 64;
  const strHex = cleanData.slice(strStart, strStart + length * 2);
  
  return Buffer.from(strHex, "hex").toString("utf8");
}

/**
 * Decode dynamic bytes from ABI-encoded hex data.
 * @param data Hex string (with or without 0x prefix)
 * @param offset Word offset where the bytes pointer is located
 * @returns Uint8Array of decoded bytes
 */
export function decodeBytes(data: string, offset: number = 0): Uint8Array {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  // Read the offset pointer
  const pointerHex = cleanData.slice(offset * 64, offset * 64 + 64);
  const pointer = Number(BigInt("0x" + pointerHex));
  
  const wordOffset = pointer / 32;
  
  // Read length
  const lengthHex = cleanData.slice(wordOffset * 64, wordOffset * 64 + 64);
  const length = Number(BigInt("0x" + lengthHex));
  
  // Read raw bytes
  const bytesStart = (wordOffset + 1) * 64;
  const bytesHex = cleanData.slice(bytesStart, bytesStart + length * 2);
  
  return Uint8Array.from(Buffer.from(bytesHex, "hex"));
}

/**
 * Decode a dynamic array of fixed-size elements.
 * @param data Hex string
 * @param elementType The ABI type of array elements
 * @param offset Word offset where array pointer is located
 * @returns Array of decoded values
 */
export function decodeArray(data: string, elementType: AbiType, offset: number = 0): any[] {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  // Read offset pointer
  const pointerHex = cleanData.slice(offset * 64, offset * 64 + 64);
  const pointer = Number(BigInt("0x" + pointerHex));
  const wordOffset = pointer / 32;
  
  // Read array length
  const lengthHex = cleanData.slice(wordOffset * 64, wordOffset * 64 + 64);
  const length = Number(BigInt("0x" + lengthHex));
  
  const results: any[] = [];
  const dataStart = wordOffset + 1;
  
  for (let i = 0; i < length; i++) {
    switch (elementType) {
      case "uint256":
        results.push(decodeUint256(cleanData.slice((dataStart + i) * 64, (dataStart + i + 1) * 64)));
        break;
      case "address":
        results.push(decodeAddress(cleanData.slice((dataStart + i) * 64, (dataStart + i + 1) * 64)));
        break;
      case "bool":
        results.push(decodeBool(cleanData.slice((dataStart + i) * 64, (dataStart + i + 1) * 64)));
        break;
      case "bytes32":
        results.push("0x" + cleanData.slice((dataStart + i) * 64, (dataStart + i + 1) * 64));
        break;
      default:
        throw new Error(`Unsupported array element type: ${elementType}`);
    }
  }
  
  return results;
}

/**
 * Decode a tuple (struct) with mixed static and dynamic types.
 * @param data Hex string
 * @param types Array of ABI types in order
 * @returns Object with decoded values keyed by index
 */
export function decodeTuple(data: string, types: AbiType[]): Record<number, any> {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  const result: Record<number, any> = {};
  
  let staticOffset = 0;
  
  for (let i = 0; i < types.length; i++) {
    const type = types[i];
    
    if (type === "string") {
      result[i] = decodeString(cleanData, staticOffset);
      staticOffset += 1;
    } else if (type === "bytes") {
      result[i] = decodeBytes(cleanData, staticOffset);
      staticOffset += 1;
    } else if (type === "array") {
      // For simplicity, assume uint256 arrays when type is generic "array"
      result[i] = decodeArray(cleanData, "uint256", staticOffset);
      staticOffset += 1;
    } else if (type === "uint256") {
      result[i] = decodeUint256(cleanData.slice(staticOffset * 64, (staticOffset + 1) * 64));
      staticOffset += 1;
    } else if (type === "address") {
      result[i] = decodeAddress(cleanData.slice(staticOffset * 64, (staticOffset + 1) * 64));
      staticOffset += 1;
    } else if (type === "bool") {
      result[i] = decodeBool(cleanData.slice(staticOffset * 64, (staticOffset + 1) * 64));
      staticOffset += 1;
    } else if (type === "bytes32") {
      result[i] = "0x" + cleanData.slice(staticOffset * 64, (staticOffset + 1) * 64);
      staticOffset += 1;
    } else {
      throw new Error(`Unsupported tuple type: ${type}`);
    }
  }
  
  return result;
}
