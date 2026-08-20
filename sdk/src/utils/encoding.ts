// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType =
  | "uint256"
  | "address"
  | "bytes32"
  | "string"
  | "bool"
  | "bytes"
  | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | Uint8Array | AbiParam[];
  components?: AbiParam[]; // For tuple types
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > 2n ** 256n - 1n) {
    throw new Error("uint256 overflow");
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
  if (!hex.startsWith("0x")) {
    throw new Error("Invalid hex: missing 0x prefix");
  }
  const cleaned = hex.slice(2);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("Invalid hex characters");
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const padded = slot.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const raw = slot.padStart(64, "0").slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot.padStart(64, "0")) !== 0n;
}

/**
 * Decode a dynamic string from ABI-encoded calldata.
 * Reads offset at current position, then length + UTF-8 data at that offset.
 */
export function decodeString(data: string, offsetWords: number = 0): string {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  const offsetHex = cleanData.substring(offsetWords * 64, offsetWords * 64 + 64);
  const byteOffset = Number(decodeUint256(offsetHex));
  const wordOffset = byteOffset / 32;

  const lengthHex = cleanData.substring(wordOffset * 64, wordOffset * 64 + 64);
  const length = Number(decodeUint256(lengthHex));

  const dataStart = wordOffset * 64 + 64;
  const hexChars = length * 2;
  const strHex = cleanData.substring(dataStart, dataStart + hexChars);
  return Buffer.from(strHex, "hex").toString("utf-8");
}

/**
 * Decode dynamic bytes from ABI-encoded calldata.
 */
export function decodeBytes(data: string, offsetWords: number = 0): Uint8Array {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  const offsetHex = cleanData.substring(offsetWords * 64, offsetWords * 64 + 64);
  const byteOffset = Number(decodeUint256(offsetHex));
  const wordOffset = byteOffset / 32;

  const lengthHex = cleanData.substring(wordOffset * 64, wordOffset * 64 + 64);
  const length = Number(decodeUint256(lengthHex));

  const dataStart = wordOffset * 64 + 64;
  const hexChars = length * 2;
  const bytesHex = cleanData.substring(dataStart, dataStart + hexChars);
  return Uint8Array.from(Buffer.from(bytesHex, "hex"));
}

/**
 * Decode a dynamic array of a given element type.
 */
export function decodeArray(
  data: string,
  elementType: AbiType,
  offsetWords: number = 0
): any[] {
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;
  const offsetHex = cleanData.substring(offsetWords * 64, offsetWords * 64 + 64);
  const byteOffset = Number(decodeUint256(offsetHex));
  const wordOffset = byteOffset / 32;

  const lengthHex = cleanData.substring(wordOffset * 64, wordOffset * 64 + 64);
  const length = Number(decodeUint256(lengthHex));

  const results: any[] = [];
  const elemDataStart = wordOffset + 1;

  for (let i = 0; i < length; i++) {
    const pos = elemDataStart + i;
    switch (elementType) {
      case "uint256":
        results.push(
          decodeUint256(cleanData.substring(pos * 64, pos * 64 + 64))
        );
        break;
      case "address":
        results.push(
          decodeAddress(cleanData.substring(pos * 64, pos * 64 + 64))
        );
        break;
      case "bool":
        results.push(
          decodeBool(cleanData.substring(pos * 64, pos * 64 + 64))
        );
        break;
      case "string":
        results.push(decodeString(data, pos));
        break;
      case "bytes":
        results.push(decodeBytes(data, pos));
        break;
      default:
        results.push(cleanData.substring(pos * 64, pos * 64 + 64));
    }
  }
  return results;
}

/**
 * Decode a tuple (struct) from ABI-encoded data using component definitions.
 */
export function decodeTuple(
  data: string,
  components: AbiParam[],
  offsetWords: number = 0
): Record<string, any> {
  const result: Record<string, any> = {};
  const cleanData = data.startsWith("0x") ? data.slice(2) : data;

  for (let i = 0; i < components.length; i++) {
    const comp = components[i];
    const pos = offsetWords + i;
    const slot = cleanData.substring(pos * 64, pos * 64 + 64);

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
      case "string":
        result[comp.value as string || `field_${i}`] = decodeString(data, pos);
        break;
      case "bytes":
        result[comp.value as string || `field_${i}`] = decodeBytes(data, pos);
        break;
      case "tuple":
        result[comp.value as string || `field_${i}`] = decodeTuple(
          data,
          comp.components || [],
          pos
        );
        break;
      default:
        result[comp.value as string || `field_${i}`] = slot;
    }
  }
  return result;
}

/**
 * Universal decodeParameter that handles both static and dynamic types.
 */
export function decodeParameter(
  data: string,
  type: AbiType,
  wordIndex: number = 0,
  components?: AbiParam[]
): any {
  switch (type) {
    case "uint256":
      return decodeUint256(
        data.startsWith("0x")
          ? data.slice(2).substring(wordIndex * 64, wordIndex * 64 + 64)
          : data.substring(wordIndex * 64, wordIndex * 64 + 64)
      );
    case "address":
      return decodeAddress(
        data.startsWith("0x")
          ? data.slice(2).substring(wordIndex * 64, wordIndex * 64 + 64)
          : data.substring(wordIndex * 64, wordIndex * 64 + 64)
      );
    case "bool":
      return decodeBool(
        data.startsWith("0x")
          ? data.slice(2).substring(wordIndex * 64, wordIndex * 64 + 64)
          : data.substring(wordIndex * 64, wordIndex * 64 + 64)
      );
    case "string":
      return decodeString(data, wordIndex);
    case "bytes":
      return decodeBytes(data, wordIndex);
    case "tuple":
      return decodeTuple(data, components || [], wordIndex);
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
