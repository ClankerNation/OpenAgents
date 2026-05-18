/**
 * @fix-author korpo1337
 * @date 2026-05-18
 * @runtime os=Linux arch=x86_64 working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
 *
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Fixed: overflow check in encodeUint256, 0x validation in decodeHex,
 * left-padding in decodeUint256, dynamic string encoding in encodeParams,
 * keccak256 in functionSelector, and added dynamic type decoding
 * (string, bytes, arrays, tuples) via decodeParameter.
 */

import { createHash } from "crypto";
import { ethers } from "ethers";

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

export interface TupleField {
  type: string;
  name?: string;
}

// ──────────────────────────────────────────────
// Encoding
// ──────────────────────────────────────────────

const UINT256_MAX = (1n << 256n) - 1n;

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n) {
    throw new Error(`encodeUint256: negative value ${n}`);
  }
  if (n > UINT256_MAX) {
    throw new Error(`encodeUint256: value ${n} overflows uint256`);
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

/**
 * Encode a single ABI parameter using dynamic head/tail encoding for strings.
 */
function encodeSingleParam(param: AbiParam): { head: string; tail: string } {
  switch (param.type) {
    case "uint256":
      return { head: encodeUint256(BigInt(param.value as number)), tail: "" };
    case "address":
      return { head: encodeAddress(param.value as string), tail: "" };
    case "bytes32":
      return { head: encodeBytes32(param.value as string), tail: "" };
    case "bool":
      return { head: encodeBool(param.value as boolean), tail: "" };
    case "string": {
      // Dynamic encoding: head = offset to tail, tail = length + data + padding
      const hexData = Buffer.from(param.value as string, "utf-8").toString("hex");
      const dataPadded = hexData.padEnd(Math.ceil(hexData.length / 64) * 64 || 64, "0");
      const lengthSlot = (hexData.length / 2).toString(16).padStart(64, "0");
      // head will be replaced with offset during assembly
      return { head: "__DYNAMIC__", tail: lengthSlot + dataPadded };
    }
    default:
      throw new Error(`encodeSingleParam: unsupported type ${param.type}`);
  }
}

export function encodeParams(params: AbiParam[]): string {
  let result = "";
  const heads: string[] = [];
  const tails: string[] = [];
  let tailOffset = params.length * 32; // head area = numParams * 32 bytes

  for (const param of params) {
    if (param.type === "string") {
      // Dynamic type: head = offset to tail data
      const hexData = Buffer.from(param.value as string, "utf-8").toString("hex");
      const dataPadded = hexData.padEnd(Math.ceil(hexData.length / 64) * 64 || 64, "0");
      const lengthSlot = (hexData.length / 2).toString(16).padStart(64, "0");
      const offsetHex = tailOffset.toString(16).padStart(64, "0");
      heads.push(offsetHex);
      tails.push(lengthSlot + dataPadded);
      tailOffset += 32 + dataPadded.length / 2; // length word + data
    } else {
      // Static type: head = encoded value, no tail
      let encoded: string;
      switch (param.type) {
        case "uint256":
          encoded = encodeUint256(BigInt(param.value as number));
          break;
        case "address":
          encoded = encodeAddress(param.value as string);
          break;
        case "bytes32":
          encoded = encodeBytes32(param.value as string);
          break;
        case "bool":
          encoded = encodeBool(param.value as boolean);
          break;
        default:
          throw new Error(`encodeParams: unsupported type ${param.type}`);
      }
      heads.push(encoded);
    }
  }

  result = "0x" + heads.join("") + tails.join("");
  return result;
}

// ──────────────────────────────────────────────
// Decoding
// ──────────────────────────────────────────────

export function decodeHex(hex: string): bigint {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (cleaned.length === 0) {
    throw new Error("decodeHex: empty hex string");
  }
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error(`decodeHex: invalid hex characters in "${cleaned}"`);
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  // Strip 0x prefix if present, then left-pad to 64 chars
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  if (cleaned.length > 64) {
    throw new Error(`decodeUint256: value exceeds 32 bytes (${cleaned.length} hex chars)`);
  }
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

export function functionSelector(signature: string): string {
  // Use proper keccak256 (Ethereum's hash) instead of sha3-256 (NIST SHA-3)
  // They produce different results — EVM uses keccak256 (pre-NIST SHA-3)
  const hash = ethers.keccak256(ethers.toUtf8Bytes(signature));
  return hash.slice(0, 10); // "0x" + first 4 bytes = 10 chars
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}

// ──────────────────────────────────────────────
// Dynamic type decoding
// ──────────────────────────────────────────────

function readSlot(hex: string, byteOffset: number): string {
  // Read 32 bytes (64 hex chars) from hex string at byte offset
  const hexOffset = byteOffset * 2;
  if (hex.startsWith("0x")) {
    const start = 2 + hexOffset;
    return hex.slice(start, start + 64);
  }
  const start = hexOffset;
  return hex.slice(start, start + 64);
}

function readBytes(hex: string, byteOffset: number, numBytes: number): string {
  const hexOffset = byteOffset * 2;
  const start = (hex.startsWith("0x") ? 2 : 0) + hexOffset;
  return hex.slice(start, start + numBytes * 2);
}

/**
 * Decode an ABI-encoded parameter.
 *
 * @param type - The ABI type string (uint256, address, bool, bytes32, string, bytes, uint256[], address[], bool[], bytes32[], tuple)
 * @param hex - The full ABI-encoded hex string (with 0x prefix)
 * @param byteOffset - The byte offset where this parameter's data begins
 * @param tupleFields - For tuple types, the field definitions
 */
export function decodeParameter(
  type: string,
  hex: string,
  byteOffset: number = 0,
  tupleFields?: TupleField[]
): unknown {
  // Determine if this type is dynamic
  const isDynamic =
    type === "string" ||
    type === "bytes" ||
    type.endsWith("[]") ||
    type.startsWith("tuple") ||
    type === "bytes[]";

  if (type === "uint256") {
    const slot = readSlot(hex, byteOffset);
    return decodeUint256(slot);
  }

  if (type === "address") {
    const slot = readSlot(hex, byteOffset);
    return decodeAddress(slot);
  }

  if (type === "bool") {
    const slot = readSlot(hex, byteOffset);
    return decodeBool(slot);
  }

  if (type === "bytes32") {
    const slot = readSlot(hex, byteOffset);
    const cleaned = slot.startsWith("0x") ? slot : "0x" + slot;
    return cleaned;
  }

  if (type === "string") {
    // Dynamic: the slot at byteOffset contains an offset to the string data
    const offsetSlot = readSlot(hex, byteOffset);
    const dataStart = byteOffset + Number(decodeUint256(offsetSlot));

    // Read length
    const lengthSlot = readSlot(hex, dataStart);
    const length = Number(decodeUint256(lengthSlot));

    // Read string bytes
    if (length === 0) return "";

    const hexData = readBytes(hex, dataStart + 32, length);
    return Buffer.from(hexData, "hex").toString("utf-8");
  }

  if (type === "bytes") {
    // Dynamic: offset to bytes data
    const offsetSlot = readSlot(hex, byteOffset);
    const dataStart = byteOffset + Number(decodeUint256(offsetSlot));

    // Read length
    const lengthSlot = readSlot(hex, dataStart);
    const length = Number(decodeUint256(lengthSlot));

    // Read bytes
    if (length === 0) return new Uint8Array(0);

    const hexData = readBytes(hex, dataStart + 32, length);
    return Uint8Array.from(Buffer.from(hexData, "hex"));
  }

  if (type === "uint256[]") {
    return decodeArray(hex, byteOffset, "uint256");
  }

  if (type === "address[]") {
    return decodeArray(hex, byteOffset, "address");
  }

  if (type === "bool[]") {
    return decodeArray(hex, byteOffset, "bool");
  }

  if (type === "bytes32[]") {
    return decodeArray(hex, byteOffset, "bytes32");
  }

  if (type === "string[]") {
    return decodeArray(hex, byteOffset, "string");
  }

  if (type === "bytes[]") {
    return decodeArray(hex, byteOffset, "bytes");
  }

  if (type === "tuple" || type.startsWith("tuple")) {
    if (!tupleFields || tupleFields.length === 0) {
      throw new Error("decodeParameter: tuple type requires tupleFields parameter");
    }

    // Determine if the tuple itself contains any dynamic fields.
    // A tuple with only static fields may be encoded inline (no offset pointer).
    const hasAnyDynamic = tupleFields.some(f =>
      f.type === "string" ||
      f.type === "bytes" ||
      f.type.endsWith("[]") ||
      f.type.startsWith("tuple")
    );

    let tupleStart: number;

    if (hasAnyDynamic) {
      // Dynamic tuple: the slot at byteOffset is an offset pointer
      const offsetSlot = readSlot(hex, byteOffset);
      tupleStart = byteOffset + Number(decodeUint256(offsetSlot));
    } else {
      // All-static tuple: data starts directly at byteOffset
      tupleStart = byteOffset;
    }

    const result: Record<string, unknown> = {};
    let fieldOffset = 0;

    for (let i = 0; i < tupleFields.length; i++) {
      const field = tupleFields[i];
      const fieldName = field.name || `field${i}`;
      const fieldType = field.type;
      const fieldIsDynamic =
        fieldType === "string" ||
        fieldType === "bytes" ||
        fieldType.endsWith("[]") ||
        fieldType.startsWith("tuple");

      if (fieldIsDynamic) {
        // Dynamic fields store an offset relative to tuple start
        const relOffsetSlot = readSlot(hex, tupleStart + fieldOffset);
        const relOffset = Number(decodeUint256(relOffsetSlot));
        const absOffset = tupleStart + relOffset;

        if (fieldType === "string") {
          // At absOffset, read length then string bytes directly
          const lengthSlot = readSlot(hex, absOffset);
          const length = Number(decodeUint256(lengthSlot));
          if (length === 0) {
            result[fieldName] = "";
          } else {
            const hexData = readBytes(hex, absOffset + 32, length);
            result[fieldName] = Buffer.from(hexData, "hex").toString("utf-8");
          }
        } else if (fieldType === "bytes") {
          // At absOffset, read length then raw bytes directly
          const lengthSlot = readSlot(hex, absOffset);
          const length = Number(decodeUint256(lengthSlot));
          if (length === 0) {
            result[fieldName] = new Uint8Array(0);
          } else {
            const hexData = readBytes(hex, absOffset + 32, length);
            result[fieldName] = Uint8Array.from(Buffer.from(hexData, "hex"));
          }
        } else if (fieldType.endsWith("[]") || fieldType.startsWith("tuple")) {
          // For arrays and nested tuples, use decodeParameter which reads an offset pointer first
          result[fieldName] = decodeParameter(
            fieldType,
            hex,
            tupleStart + fieldOffset, // pass the head slot position (contains offset)
            fieldType.startsWith("tuple") || fieldType === "tuple"
              ? (field as any).tupleFields || (field as any).components
              : undefined
          );
        } else {
          // Fallback for other dynamic types
          result[fieldName] = decodeParameter(fieldType, hex, absOffset);
        }
      } else {
        result[fieldName] = decodeParameter(fieldType, hex, tupleStart + fieldOffset);
      }

      fieldOffset += 32; // each head slot is 32 bytes
    }

    return result;
  }

  throw new Error(`decodeParameter: unsupported type "${type}"`);
}

function decodeArray(hex: string, byteOffset: number, elementType: string): unknown[] {
  // Read offset to array data
  const offsetSlot = readSlot(hex, byteOffset);
  const dataStart = byteOffset + Number(decodeUint256(offsetSlot));

  // Read array length
  const lengthSlot = readSlot(hex, dataStart);
  const length = Number(decodeUint256(lengthSlot));

  if (length === 0) return [];

  const elementIsDynamic =
    elementType === "string" ||
    elementType === "bytes" ||
    elementType.endsWith("[]") ||
    elementType.startsWith("tuple");

  const result: unknown[] = [];

  if (elementIsDynamic) {
    // Head area: length + (length * 32 bytes of offsets)
    for (let i = 0; i < length; i++) {
      const elemOffsetSlot = readSlot(hex, dataStart + 32 + i * 32);
      const elemRelOffset = Number(decodeUint256(elemOffsetSlot));
      result.push(
        decodeParameter(elementType, hex, dataStart + 32 + elemRelOffset)
      );
    }
  } else {
    // Static elements: packed sequentially after the length
    for (let i = 0; i < length; i++) {
      result.push(
        decodeParameter(elementType, hex, dataStart + 32 + i * 32)
      );
    }
  }

  return result;
}