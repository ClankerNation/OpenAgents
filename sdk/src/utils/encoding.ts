// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | Uint8Array | AbiParam[];
  components?: AbiParam[]; // For tuple types
}

const MAX_UINT256 = BigInt("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new Error(`encodeUint256: overflow or underflow for value ${value}`);
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
      case "string": {
        const hexStr = Buffer.from(param.value as string).toString("hex");
        encoded += hexStr.padEnd(64, "0");
        break;
      }
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  if (!hex) return 0n;
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error(`decodeHex: invalid hex string "${hex}"`);
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const padded = slot.padStart(64, "0");
  return decodeHex(padded);
}

export function decodeAddress(slot: string): string {
  const raw = slot.padStart(64, "0").slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return decodeHex(slot) !== 0n;
}

/**
 * Decode a dynamic string from ABI-encoded hex data.
 * Format: offset (32 bytes) -> length (32 bytes) -> utf8 data (padded to 32 bytes)
 * @param data Full ABI-encoded hex string (with 0x prefix)
 * @param offset Byte offset where the string head starts (default 0)
 */
export function decodeString(data: string, offset: number = 0): string {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  // Read the offset pointer at the given position
  const offsetHex = cleanData.substring(offset * 2, offset * 2 + 64);
  const dataOffset = Number(decodeHex(offsetHex));
  
  // At the data offset, read length
  const lengthHex = cleanData.substring(dataOffset * 2, dataOffset * 2 + 64);
  const length = Number(decodeHex(lengthHex));
  
  // Read the actual string bytes
  const strHex = cleanData.substring(dataOffset * 2 + 64, dataOffset * 2 + 64 + length * 2);
  return Buffer.from(strHex, "hex").toString("utf8");
}

/**
 * Decode dynamic bytes from ABI-encoded hex data.
 * Format: offset (32 bytes) -> length (32 bytes) -> raw data (padded to 32 bytes)
 */
export function decodeBytes(data: string, offset: number = 0): Uint8Array {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  const offsetHex = cleanData.substring(offset * 2, offset * 2 + 64);
  const dataOffset = Number(decodeHex(offsetHex));
  
  const lengthHex = cleanData.substring(dataOffset * 2, dataOffset * 2 + 64);
  const length = Number(decodeHex(lengthHex));
  
  const bytesHex = cleanData.substring(dataOffset * 2 + 64, dataOffset * 2 + 64 + length * 2);
  return Uint8Array.from(Buffer.from(bytesHex, "hex"));
}

/**
 * Decode a dynamic array of fixed-size elements from ABI-encoded hex data.
 * Supports uint256, address, bool, bytes32 element types.
 * Format: offset -> length -> elements (each 32 bytes)
 */
export function decodeArray(
  data: string,
  elementType: AbiType,
  offset: number = 0
): (string | bigint | boolean)[] {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  
  const offsetHex = cleanData.substring(offset * 2, offset * 2 + 64);
  const dataOffset = Number(decodeHex(offsetHex));
  
  const lengthHex = cleanData.substring(dataOffset * 2, dataOffset * 2 + 64);
  const length = Number(decodeHex(lengthHex));
  
  const result: (string | bigint | boolean)[] = [];
  const elemStart = dataOffset + 32; // skip length word
  
  for (let i = 0; i < length; i++) {
    const elemOffset = (elemStart + i * 32) * 2;
    const slot = cleanData.substring(elemOffset, elemOffset + 64);
    
    switch (elementType) {
      case "uint256":
        result.push(decodeUint256(slot));
        break;
      case "address":
        result.push(decodeAddress(slot));
        break;
      case "bool":
        result.push(decodeBool(slot));
        break;
      case "bytes32":
        result.push("0x" + slot);
        break;
      default:
        throw new Error(`decodeArray: unsupported element type ${elementType}`);
    }
  }
  
  return result;
}

/**
 * Decode a tuple (struct) from ABI-encoded hex data.
 * Each component is decoded according to its type at sequential 32-byte slots.
 */
export function decodeTuple(
  data: string,
  components: AbiParam[],
  offset: number = 0
): Record<string, string | bigint | boolean | Uint8Array | Record<string, unknown>> {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  const result: Record<string, unknown> = {};
  
  for (let i = 0; i < components.length; i++) {
    const comp = components[i];
    const slotStart = (offset + i * 32) * 2;
    const slot = cleanData.substring(slotStart, slotStart + 64);
    
    switch (comp.type) {
      case "uint256":
        result[comp.value as string || `field_${i}`] = decodeUint256(slot);
        break;
      case "address":
        result[comp.value as string || `field_${i}`] = decodeAddress(slot);
        break;
      case "bool":
        result[comp.value as string || `field_${i}`] = decodeBool(slot);
        break;
      case "bytes32":
        result[comp.value as string || `field_${i}`] = "0x" + slot;
        break;
      case "string":
        result[comp.value as string || `field_${i}`] = decodeString(data, offset + i * 32);
        break;
      case "bytes":
        result[comp.value as string || `field_${i}`] = decodeBytes(data, offset + i * 32);
        break;
      case "tuple":
        if (comp.components) {
          result[comp.value as string || `field_${i}`] = decodeTuple(data, comp.components, offset + i * 32);
        }
        break;
      default:
        result[comp.value as string || `field_${i}`] = "0x" + slot;
    }
  }
  
  return result as Record<string, string | bigint | boolean | Uint8Array | Record<string, unknown>>;
}

/**
 * Generic decodeParameter that dispatches to the correct decoder based on type.
 */
export function decodeParameter(
  data: string,
  type: AbiType,
  components?: AbiParam[]
): string | bigint | boolean | Uint8Array | (string | bigint | boolean)[] | Record<string, unknown> {
  switch (type) {
    case "uint256":
      return decodeUint256(data);
    case "address":
      return decodeAddress(data);
    case "bool":
      return decodeBool(data);
    case "bytes32":
      return data.startsWith("0x") ? data : "0x" + data;
    case "string":
      return decodeString(data);
    case "bytes":
      return decodeBytes(data);
    case "tuple":
      if (!components) throw new Error("decodeParameter: tuple requires components");
      return decodeTuple(data, components);
    default:
      throw new Error(`decodeParameter: unsupported type ${type}`);
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
