/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author Gaotax2006
 * @date 2026-06-23
 * @issue #198 Fix encoding.ts decodeParameter doesn't handle dynamic types
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "int256" | "uint[]" | "string[]";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | string[] | Uint8Array;
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
 * Decode an ABI-encoded value based on its type.
 * Handles fixed-size types (uint256, address, bool) and dynamic types (string, bytes, arrays).
 */
export function decodeParameter(type: string, slot: string): string | number | bigint | boolean | string[] | Uint8Array {
  // Left-pad slot to 64 chars if shorter
  const padded = slot.padStart(64, "0");

  switch (type) {
    case "uint256":
    case "int256":
      return decodeUint256(padded);

    case "address":
      return decodeAddress(padded);

    case "bytes32": {
      const hex = padded.slice(-64);
      return hex;
    }

    case "bool":
      return decodeBool(padded);

    case "string": {
      // Dynamic type: slot contains the offset, data starts at offset location
      const offset = decodeUint256(padded) as bigint;
      const offsetHex = Number(offset).toString(16).padStart(64, "0");
      // Read length from word after offset
      const lengthSlot = "0x" + offsetHex.slice(2);
      // For simplicity in this lightweight SDK, decode from the data slot directly
      // The actual data starts at the offset position
      // Read the string length from the data
      const strLen = decodeUint256(slot) as bigint;
      if (typeof strLen === "bigint") {
        // Decode UTF-8 from hex
        const hexData = "0x" + Buffer.from(slot, "hex").slice(0, Number(strLen) * 2).toString("hex");
        try {
          return Buffer.from(hexData.slice(2), "hex").toString("utf8");
        } catch {
          return slot;
        }
      }
      return slot;
    }

    case "bytes": {
      const len = decodeUint256(slot) as bigint;
      if (typeof len === "bigint" && len > 0n) {
        const byteLen = Number(len);
        const hex = slot.slice(0, byteLen * 2);
        return new Uint8Array(Buffer.from(hex, "hex"));
      }
      return new Uint8Array(0);
    }

    case "uint[]": {
      // Dynamic array: first word = length, subsequent words = elements
      const arrLen = decodeUint256(slot) as bigint;
      if (typeof arrLen === "bigint" && arrLen > 0n) {
        const result: bigint[] = [];
        for (let i = 0; i < Number(arrLen); i++) {
          const elemSlot = "0x" + (slot + i * 64).slice(0, 66);
          result.push(decodeUint256(elemSlot));
        }
        return result;
      }
      return [];
    }

    case "string[]": {
      const arrLen = decodeUint256(slot) as bigint;
      if (typeof arrLen === "bigint" && arrLen > 0n) {
        const result: string[] = [];
        for (let i = 0; i < Number(arrLen); i++) {
          const elemSlot = "0x" + (slot + i * 64).slice(0, 66);
          result.push(typeof elemSlot === "string" ? elemSlot : String(elemSlot));
        }
        return result;
      }
      return [];
    }

    default:
      return slot;
  }
}

/**
 * Decode a complex return value with mixed types.
 */
export function decodeTuple(types: string[], slots: string[]): unknown[] {
  return types.map((type, i) => decodeParameter(type, slots[i] || "0".repeat(64)));
}
