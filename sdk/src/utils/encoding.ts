/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | AbiParam[] | Uint8Array;
  components?: AbiParam[];
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n >= 1n << 256n) throw new Error("uint256 overflow");
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  if (cleaned.length !== 40) throw new Error("Invalid address length");
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  if (cleaned.length > 64) throw new Error("bytes32 too long");
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

function encodeDynamic(data: string): string {
  const len = data.length / 2;
  const paddedLen = len.toString(16).padStart(64, "0");
  const paddedData = data.padEnd(Math.ceil(len / 32) * 64, "0");
  return paddedLen + paddedData;
}

export function encodeParams(params: AbiParam[]): string {
  let staticPart = "";
  const dynamicPart: string[] = [];
  let dynamicOffset = params.length * 32;

  for (const param of params) {
    switch (param.type) {
      case "uint256":
      case "address":
      case "bytes32":
      case "bool":
        staticPart += encodeParam(param);
        break;
      case "string": {
        const hex = Buffer.from(param.value as string, "utf8").toString("hex");
        staticPart += encodeUint256(dynamicOffset);
        dynamicPart.push(encodeDynamic(hex));
        dynamicOffset += 32 + Math.ceil(hex.length / 64) * 64;
        break;
      }
      case "bytes": {
        const hex = typeof param.value === "string" && (param.value as string).startsWith("0x")
          ? (param.value as string).slice(2) : Buffer.from(param.value as Uint8Array).toString("hex");
        staticPart += encodeUint256(dynamicOffset);
        dynamicPart.push(encodeDynamic(hex));
        dynamicOffset += 32 + Math.ceil(hex.length / 64) * 64;
        break;
      }
      case "tuple": {
        const tupleEncoded = encodeParams(param.components || []);
        staticPart += encodeUint256(dynamicOffset);
        dynamicPart.push(tupleEncoded.slice(2));
        dynamicOffset += 32 + Math.ceil((tupleEncoded.length - 2) / 64) * 32;
        break;
      }
    }
  }

  return "0x" + staticPart + dynamicPart.join("");
}

function encodeParam(param: AbiParam): string {
  switch (param.type) {
    case "uint256": return encodeUint256(BigInt(param.value as number));
    case "address": return encodeAddress(param.value as string);
    case "bytes32": return encodeBytes32(param.value as string);
    case "bool": return encodeBool(param.value as boolean);
    default: throw new Error("Unsupported static type: " + param.type);
  }
}

export function decodeHex(hex: string): bigint {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) throw new Error("Invalid hex string");
  if (cleaned.length === 0) return 0n;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  const padded = cleaned.padStart(64, "0").slice(0, 64);
  return BigInt("0x" + padded);
}

export function decodeAddress(slot: string): string {
  const hex = slot.startsWith("0x") ? slot.slice(2) : slot;
  const raw = hex.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  const hex = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + hex.padStart(64, "0")) !== 0n;
}

export function decodeString(data: string, offset: number): string {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const dataOffset = parseInt(hex.substring(offset * 64, offset * 64 + 64), 16);
  const strLen = parseInt(hex.substring((offset + dataOffset / 32) * 64, (offset + dataOffset / 32) * 64 + 64), 16);
  const strHex = hex.substring((offset + dataOffset / 32 + 1) * 64, (offset + dataOffset / 32 + 1) * 64 + strLen * 2);
  return Buffer.from(strHex, "hex").toString("utf8");
}

export function decodeBytes(data: string, offset: number): Uint8Array {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const dataOffset = parseInt(hex.substring(offset * 64, offset * 64 + 64), 16);
  const byteLen = parseInt(hex.substring((offset + dataOffset / 32) * 64, (offset + dataOffset / 32) * 64 + 64), 16);
  const byteHex = hex.substring((offset + dataOffset / 32 + 1) * 64, (offset + dataOffset / 32 + 1) * 64 + byteLen * 2);
  return Buffer.from(byteHex, "hex");
}

export function decodeArray(data: string, offset: number, elemType: AbiType): any[] {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const dataOffset = parseInt(hex.substring(offset * 64, offset * 64 + 64), 16);
  const arrLen = parseInt(hex.substring((offset + dataOffset / 32) * 64, (offset + dataOffset / 32) * 64 + 64), 16);
  const result = [];
  for (let i = 0; i < arrLen; i++) {
    const slot = hex.substring((offset + dataOffset / 32 + 1 + i) * 64, (offset + dataOffset / 32 + 1 + i) * 64 + 64);
    result.push(decodeSlot(slot, elemType));
  }
  return result;
}

export function decodeSlot(slot: string, type: AbiType): any {
  switch (type) {
    case "uint256": return decodeUint256(slot);
    case "address": return decodeAddress(slot);
    case "bool": return decodeBool(slot);
    default: return decodeUint256(slot);
  }
}

export function decodeParameter(data: string, type: AbiType): any {
  if (type === "string") return decodeString(data, 0);
  if (type === "bytes") return decodeBytes(data, 0);
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  return decodeSlot(hex.substring(0, 64), type);
}

export function decodeParameters(data: string, types: AbiType[]): any[] {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const result: any[] = [];
  const dynamicValues: { idx: number; type: AbiType; dataOffset: number }[] = [];
  for (let i = 0; i < types.length; i++) {
    const type = types[i];
    const slot = hex.substring(i * 64, i * 64 + 64);
    if (type === "string" || type === "bytes") {
      dynamicValues.push({ idx: i, type, dataOffset: parseInt(slot, 16) });
      result.push(null);
    } else {
      result.push(decodeSlot(slot, type));
    }
  }
  for (const dv of dynamicValues) {
    const startSlot = dv.dataOffset / 32;
    if (dv.type === "string") result[dv.idx] = decodeString(data, startSlot);
    else if (dv.type === "bytes") result[dv.idx] = decodeBytes(data, startSlot);
  }
  return result;
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
