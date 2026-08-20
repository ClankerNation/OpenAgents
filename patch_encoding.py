import re

with open('sdk/src/utils/encoding.ts', 'r') as f:
    content = f.read()

# Add contributor header at the very top
header = """/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
"""
if not content.startswith("/**\n * @contributor-info"):
    content = header + content

# Update AbiType to include dynamic types
old_type = 'export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";'
new_type = 'export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "tuple" | "array";'
content = content.replace(old_type, new_type)

# Add decode functions before the last closing brace or at end of file
decode_funcs = """

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
"""

# Append at end of file
content = content.rstrip() + "\n" + decode_funcs

with open('sdk/src/utils/encoding.ts', 'w') as f:
    f.write(content)

print("Patched encoding.ts")
