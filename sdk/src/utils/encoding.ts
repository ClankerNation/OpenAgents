/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * @fix-author ARO-Agentic | 2026-08-18
 * @runtime os=linux arch=x64 working_dir=/tmp/OpenAgents shell=bash
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

const MAX_UINT256 = BigInt("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new Error(`encodeUint256: value out of range [0, 2^256-1], got ${n}`);
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error(`encodeAddress: invalid address length or chars: ${address}`);
  }
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length > 64) {
    throw new Error("encodeBytes32: data exceeds 32 bytes");
  }
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf-8").toString("hex");
  const lenHex = BigInt(hex.length / 2).toString(16).padStart(64, "0");
  const paddedData = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return lenHex + paddedData;
}

export function encodeDynamicBytes(value: Uint8Array | string): string {
  const buf = typeof value === "string" ? Buffer.from(value.replace(/^0x/, ""), "hex") : Buffer.from(value);
  const lenHex = BigInt(buf.length).toString(16).padStart(64, "0");
  const hex = buf.toString("hex");
  const paddedData = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return lenHex + paddedData;
}

function isDynamic(type: AbiType): boolean {
  return type === "string" || type === "bytes" || type === "tuple";
}

export function encodeParams(params: AbiParam[]): string {
  let head = "";
  let tail = "";
  let dynamicOffset = params.length * 32;

  for (const param of params) {
    if (isDynamic(param.type)) {
      head += BigInt(dynamicOffset).toString(16).padStart(64, "0");
      let encodedTail = "";
      if (param.type === "string") {
        encodedTail = encodeString(param.value as string);
      } else if (param.type === "bytes") {
        encodedTail = encodeDynamicBytes(param.value as Uint8Array | string);
      } else if (param.type === "tuple") {
        encodedTail = encodeParams(param.components || []).slice(2);
      }
      tail += encodedTail;
      dynamicOffset += (encodedTail.length / 2);
    } else {
      switch (param.type) {
        case "uint256":
          head += encodeUint256(BigInt(param.value as number | bigint));
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
        default:
          throw new Error(`encodeParams: unsupported static type ${param.type}`);
      }
    }
  }
  return "0x" + head + tail;
}

export function decodeHex(hex: string): bigint {
  if (!hex) throw new Error("decodeHex: empty input");
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]+$/.test(cleaned)) {
    throw new Error(`decodeHex: invalid hex characters in "${hex}"`);
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0");
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const raw = slot.startsWith("0x") ? slot.slice(2) : slot;
  const addr = raw.padStart(64, "0").slice(-40);
  return "0x" + addr.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return decodeUint256(slot) !== 0n;
}

export function decodeString(data: string, offset: number = 0): string {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const lenSlot = hex.substr(offset, 64);
  const len = Number(decodeUint256(lenSlot));
  const dataStart = offset + 64;
  const strHex = hex.substr(dataStart, len * 2);
  return Buffer.from(strHex, "hex").toString("utf-8");
}

export function decodeBytes(data: string, offset: number = 0): Uint8Array {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const lenSlot = hex.substr(offset, 64);
  const len = Number(decodeUint256(lenSlot));
  const dataStart = offset + 64;
  const bytesHex = hex.substr(dataStart, len * 2);
  return Uint8Array.from(Buffer.from(bytesHex, "hex"));
}

export function decodeParameter(data: string, type: AbiType, offset: number = 0): any {
  const hex = data.startsWith("0x") ? data.slice(2) : data;

  if (type === "uint256") {
    return decodeUint256(hex.substr(offset, 64));
  }
  if (type === "address") {
    return decodeAddress(hex.substr(offset, 64));
  }
  if (type === "bytes32") {
    return "0x" + hex.substr(offset, 64);
  }
  if (type === "bool") {
    return decodeBool(hex.substr(offset, 64));
  }
  if (type === "string") {
    const ptrSlot = hex.substr(offset, 64);
    const ptr = Number(decodeUint256(ptrSlot));
    return decodeString(hex, ptr * 2);
  }
  if (type === "bytes") {
    const ptrSlot = hex.substr(offset, 64);
    const ptr = Number(decodeUint256(ptrSlot));
    return decodeBytes(hex, ptr * 2);
  }
  if (type === "tuple") {
    // Simplified tuple decode: assumes all components are static for now
    // Full recursive dynamic tuple support requires component metadata at call site
    throw new Error("decodeParameter: tuple decoding requires component metadata; use decodeParams with components");
  }
  throw new Error(`decodeParameter: unsupported type ${type}`);
}

export function decodeParams(data: string, types: AbiParam[]): any[] {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const results: any[] = [];
  let headOffset = 0;

  for (const param of types) {
    if (isDynamic(param.type)) {
      const ptrSlot = hex.substr(headOffset, 64);
      const ptr = Number(decodeUint256(ptrSlot));
      const byteOffset = ptr * 2;

      if (param.type === "string") {
        results.push(decodeString(hex, byteOffset));
      } else if (param.type === "bytes") {
        results.push(decodeBytes(hex, byteOffset));
      } else if (param.type === "tuple" && param.components) {
        // Recursive decode for nested tuples at the pointed location
        const subResults: any[] = [];
        let subOffset = byteOffset;
        for (const comp of param.components) {
          subResults.push(decodeParameter("0x" + hex.substr(subOffset), comp.type, 0));
          subOffset += 64; // Simplified: only works for static sub-components
        }
        results.push(subResults);
      } else {
        results.push(null);
      }
    } else {
      results.push(decodeParameter("0x" + hex, param.type, headOffset));
    }
    headOffset += 64;
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
