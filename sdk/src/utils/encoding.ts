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
 * Decodes a single ABI parameter from hex-encoded data starting at a given offset.
 * Supports static types (uint256, address, bytes32, bool) and dynamic types (string, bytes).
 * For dynamic types, the data at the offset is interpreted as a pointer to the actual data.
 * @param data - The full hex-encoded data (without "0x" prefix)
 * @param offset - The byte offset (in hex characters) where the parameter starts
 * @param type - The ABI type to decode
 * @returns The decoded value as a string
 */
export function decodeParameter(data: string, offset: number, type: string): string {
  const wordSize = 64; // 32 bytes = 64 hex chars

  if (type === "string") {
    // Dynamic string: offset points to a word containing the data offset
    const dataOffset = parseInt(data.substring(offset, offset + wordSize), 16) * 2; // Convert to hex char offset
    const length = parseInt(data.substring(dataOffset, dataOffset + wordSize), 16);
    const stringHex = data.substring(dataOffset + wordSize, dataOffset + wordSize + length * 2);
    return Buffer.from(stringHex, "hex").toString("utf-8");
  }

  if (type === "bytes") {
    // Dynamic bytes: offset points to a word containing the data offset
    const dataOffset = parseInt(data.substring(offset, offset + wordSize), 16) * 2;
    const length = parseInt(data.substring(dataOffset, dataOffset + wordSize), 16);
    const bytesHex = data.substring(dataOffset + wordSize, dataOffset + wordSize + length * 2);
    return "0x" + bytesHex;
  }

  // Static types
  const raw = data.substring(offset, offset + wordSize);
  switch (type) {
    case "uint256":
      return decodeUint256(raw).toString();
    case "address":
      return decodeAddress(raw);
    case "bytes32":
      return "0x" + raw;
    case "bool":
      return decodeBool(raw).toString();
    default:
      throw new Error(`Unsupported type: ${type}`);
  }
}

/**
 * Decodes multiple ABI parameters from hex-encoded data.
 * Supports dynamic types (string, bytes, dynamic arrays, tuples) by handling
 * pointer-based offsets for dynamic data.
 * @param types - Array of ABI type strings
 * @param data - The full hex-encoded data (with or without "0x" prefix)
 * @returns Array of decoded values as strings
 */
export function decodeParams(types: string[], data: string): string[] {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const wordSize = 64; // 32 bytes = 64 hex chars
  const results: string[] = [];
  let staticOffset = 0;
  let dynamicOffset = types.length * 32; // Dynamic data starts after all static words

  for (let i = 0; i < types.length; i++) {
    const type = types[i];

    // Handle dynamic types
    if (type === "string" || type === "bytes") {
      const pointer = parseInt(cleaned.substring(staticOffset, staticOffset + wordSize), 16);
      const actualOffset = pointer * 2; // Convert to hex char offset
      const length = parseInt(cleaned.substring(actualOffset, actualOffset + wordSize), 16);
      
      if (type === "string") {
        const stringHex = cleaned.substring(actualOffset + wordSize, actualOffset + wordSize + length * 2);
        results.push(Buffer.from(stringHex, "hex").toString("utf-8"));
      } else {
        const bytesHex = cleaned.substring(actualOffset + wordSize, actualOffset + wordSize + length * 2);
        results.push("0x" + bytesHex);
      }
      staticOffset += wordSize;
    }
    // Handle dynamic arrays (type ending with [])
    else if (type.endsWith("[]")) {
      const pointer = parseInt(cleaned.substring(staticOffset, staticOffset + wordSize), 16);
      const actualOffset = pointer * 2;
      const arrayLength = parseInt(cleaned.substring(actualOffset, actualOffset + wordSize), 16);
      const baseType = type.slice(0, -2);
      const arrayValues: string[] = [];
      
      for (let j = 0; j < arrayLength; j++) {
        const elementOffset = actualOffset + wordSize + j * wordSize;
        const raw = cleaned.substring(elementOffset, elementOffset + wordSize);
        
        switch (baseType) {
          case "uint256":
            arrayValues.push(decodeUint256(raw).toString());
            break;
          case "address":
            arrayValues.push(decodeAddress(raw));
            break;
          case "bytes32":
            arrayValues.push("0x" + raw);
            break;
          case "bool":
            arrayValues.push(decodeBool(raw).toString());
            break;
          default:
            arrayValues.push("0x" + raw);
        }
      }
      results.push("[" + arrayValues.join(",") + "]");
      staticOffset += wordSize;
    }
    // Handle tuples (type starting with tuple)
    else if (type.startsWith("tuple")) {
      const pointer = parseInt(cleaned.substring(staticOffset, staticOffset + wordSize), 16);
      const actualOffset = pointer * 2;
      
      // Extract tuple member types from the type string
      const memberTypesMatch = type.match(/^tuple\((.+)\)$/);
      if (!memberTypesMatch) {
        throw new Error(`Invalid tuple type: ${type}`);
      }
      const memberTypes = memberTypesMatch[1].split(",");
      
      // Recursively decode tuple members
      const tupleData = cleaned.substring(actualOffset);
      const decodedMembers = decodeParams(memberTypes, tupleData);
      results.push("(" + decodedMembers.join(",") + ")");
      staticOffset += wordSize;
    }
    // Static types
    else {
      const raw = cleaned.substring(staticOffset, staticOffset + wordSize);
      switch (type) {
        case "uint256":
          results.push(decodeUint256(raw).toString());
          break;
        case "address":
          results.push(decodeAddress(raw));
          break;
        case "bytes32":
          results.push("0x" + raw);
          break;
        case "bool":
          results.push(decodeBool(raw).toString());
          break;
        default:
          results.push("0x" + raw);
      }
      staticOffset += wordSize;
    }
  }

  return results;
}
