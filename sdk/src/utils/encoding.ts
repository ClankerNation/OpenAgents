/**
 * @fix-author Hermes Agent (Nous Research)
 * @fix-date 2026-08-04
 *
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * Fixes issue #198: decodeParameter now handles dynamic types (string, bytes,
 * dynamic arrays) and nested tuples via recursive decoding.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

const MAX_UINT256 = (1n << 256n) - 1n;

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) throw new Error("encodeUint256: overflow");
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

export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf8").toString("hex");
  const lenHex = BigInt(hex.length / 2).toString(16).padStart(64, "0");
  const padded = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return lenHex + padded;
}

export function encodeDynamicBytes(data: Uint8Array | string): string {
  const hex = typeof data === "string"
    ? (data.startsWith("0x") ? data.slice(2) : Buffer.from(data, "utf8").toString("hex"))
    : Buffer.from(data).toString("hex");
  const lenHex = BigInt(hex.length / 2).toString(16).padStart(64, "0");
  const padded = hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
  return lenHex + padded;
}

export function encodeParams(params: AbiParam[]): string {
  const headParts: string[] = [];
  const tailParts: string[] = [];

  let tailOffset = params.length * 32;
  for (const param of params) {
    if (param.type === "string") {
      headParts.push(BigInt(tailOffset).toString(16).padStart(64, "0"));
      const encoded = encodeString(param.value as string);
      tailParts.push(encoded);
      tailOffset += encoded.length / 2;
    } else if (param.type === "bytes") {
      headParts.push(BigInt(tailOffset).toString(16).padStart(64, "0"));
      const encoded = encodeDynamicBytes(param.value as string);
      tailParts.push(encoded);
      tailOffset += encoded.length / 2;
    } else {
      switch (param.type) {
        case "uint256": headParts.push(encodeUint256(BigInt(param.value as number))); break;
        case "address": headParts.push(encodeAddress(param.value as string)); break;
        case "bytes32": headParts.push(encodeBytes32(param.value as string)); break;
        case "bool": headParts.push(encodeBool(param.value as boolean)); break;
        default: headParts.push("0".repeat(64));
      }
    }
  }

  return "0x" + headParts.join("") + tailParts.join("");
}

function readSlot(hex: string, offset: number): string {
  return hex.slice(offset, offset + 64);
}

function slotToBigInt(slot: string): bigint {
  return BigInt("0x" + (slot || "0"));
}

function slotToNumber(slot: string): number {
  return Number(slotToBigInt(slot));
}

export function decodeHex(hex: string): bigint {
  if (typeof hex !== "string") throw new Error("decodeHex: expected string");
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) throw new Error("decodeHex: invalid hex");
  return BigInt("0x" + (cleaned || "0"));
}

export function decodeUint256(slot: string): bigint {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned.padStart(64, "0"));
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

export function decodeBytes32(slot: string): string {
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return "0x" + cleaned.slice(0, 64);
}

type AbiTypeDef = string | { type: string; components?: AbiTypeDef[] };

function parseTupleDef(typeStr: string): { members: AbiTypeDef[]; raw: string } | null {
  const match = typeStr.match(/^tuple\((.*)\)(\[\d*\])?$/);
  if (!match) return null;
  const inner = match[1];
  const members = parseTypeList(inner);
  return { members, raw: match[0] };
}

function parseTypeList(list: string): AbiTypeDef[] {
  const result: AbiTypeDef[] = [];
  let depth = 0;
  let current = "";
  for (let i = 0; i < list.length; i++) {
    const ch = list[i];
    if (ch === "(") {
      depth++;
      current += ch;
    } else if (ch === ")") {
      depth--;
      current += ch;
    } else if (ch === "," && depth === 0) {
      result.push(parseSingleType(current.trim()));
      current = "";
    } else {
      current += ch;
    }
  }
  if (current.trim()) {
    result.push(parseSingleType(current.trim()));
  }
  return result;
}

function parseSingleType(s: string): AbiTypeDef {
  if (s.startsWith("tuple")) {
    const t = parseTupleDef(s);
    if (t) return { type: "tuple", components: t.members };
  }
  return s;
}

export function decodeParameter(
  type: string,
  data: string
): any {
  const hex = data.startsWith("0x") ? data.slice(2) : data;

  if (type === "uint256" || type === "uint" || type === "uint8" || type === "uint16" || type === "uint32" || type === "uint64" || type === "uint128") {
    return decodeUint256("0x" + readSlot(hex, 0));
  }
  if (type === "int256" || type === "int" || type === "int8" || type === "int16" || type === "int32" || type === "int64" || type === "int128") {
    return decodeUint256("0x" + readSlot(hex, 0));
  }
  if (type === "address") {
    return decodeAddress(readSlot(hex, 0));
  }
  if (type === "bytes32") {
    return "0x" + readSlot(hex, 0);
  }
  if (type === "bool") {
    return decodeBool(readSlot(hex, 0));
  }

  const staticBytesMatch = type.match(/^bytes(\d+)$/);
  if (staticBytesMatch) {
    const n = parseInt(staticBytesMatch[1], 10);
    if (n >= 1 && n <= 32) {
      return "0x" + readSlot(hex, 0).slice(0, n * 2);
    }
  }

  if (type === "string") {
    const offset = slotToNumber(readSlot(hex, 0)) * 2;
    const len = slotToNumber(readSlot(hex, offset));
    const strHex = hex.slice(offset + 64, offset + 64 + len * 2);
    return Buffer.from(strHex, "hex").toString("utf8");
  }

  if (type === "bytes") {
    const offset = slotToNumber(readSlot(hex, 0)) * 2;
    const len = slotToNumber(readSlot(hex, offset));
    const bytesHex = hex.slice(offset + 64, offset + 64 + len * 2);
    return new Uint8Array(Buffer.from(bytesHex, "hex"));
  }

  const arrMatch = type.match(/^(.+)\[\]$/);
  if (arrMatch) {
    const elemType = arrMatch[1];
    const offset = slotToNumber(readSlot(hex, 0)) * 2;
    const arrLen = slotToNumber(readSlot(hex, offset));

    const results: any[] = [];

    const elemIsDynamic = elemType === "string" || elemType === "bytes" ||
      elemType.startsWith("tuple") || elemType.match(/\[\]$/) !== null;

    if (elemIsDynamic) {
      for (let i = 0; i < arrLen; i++) {
        const elemOffset = slotToNumber(readSlot(hex, offset + 32 + i * 64)) * 2;
        const actualOffset = offset + 32 + elemOffset;
        results.push(decodeParameter(elemType, "0x" + hex.slice(actualOffset)));
      }
    } else {
      for (let i = 0; i < arrLen; i++) {
        const es = offset + 32 + i * 64;
        results.push(decodeParameter(elemType, "0x" + readSlot(hex, es)));
      }
    }

    return results;
  }

  const fixedArrMatch = type.match(/^(.+)\[(\d+)\]$/);
  if (fixedArrMatch) {
    const elemType = fixedArrMatch[1];
    const arrLen = parseInt(fixedArrMatch[2], 10);
    const results: any[] = [];
    for (let i = 0; i < arrLen; i++) {
      results.push(decodeParameter(elemType, "0x" + readSlot(hex, i * 64)));
    }
    return results;
  }

  const tupleDef = parseTupleDef(type);
  if (tupleDef) {
    return decodeTuple(tupleDef.members, "0x" + hex);
  }

  throw new Error("decodeParameter: unsupported type \"" + type + "\"");
}

function decodeTuple(members: AbiTypeDef[], data: string): any[] {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const result: any[] = [];

  for (let slotIdx = 0; slotIdx < members.length; slotIdx++) {
    const member = members[slotIdx];
    const memberType = typeof member === "string" ? member : "tuple";
    const isDynamic = typeIsDynamic(memberType);

    if (isDynamic) {
      const offset = slotToNumber(readSlot(hex, slotIdx * 64)) * 2;
      result.push(decodeParameter(memberType, "0x" + hex.slice(offset)));
    } else {
      result.push(decodeSingleSlot(member, hex, slotIdx * 64));
    }
  }

  return result;
}

function typeIsDynamic(t: string): boolean {
  return t === "string" || t === "bytes" ||
    t.match(/\[\]$/) !== null ||
    t.startsWith("tuple");
}

function decodeSingleSlot(member: AbiTypeDef, hex: string, start: number): any {
  if (typeof member === "string") {
    return decodeParameter(member, "0x" + hex.slice(start, start + 64));
  }
  return decodeTuple(member.components || [], "0x" + hex.slice(start));
}

export function decodeParams(
  types: string[],
  data: string
): any[] {
  const hex = data.startsWith("0x") ? data.slice(2) : data;
  const results: any[] = [];

  for (let i = 0; i < types.length; i++) {
    const type = types[i];
    if (typeIsDynamic(type)) {
      const offset = slotToNumber(readSlot(hex, i * 64)) * 2;
      results.push(decodeParameter(type, "0x" + hex.slice(offset)));
    } else {
      results.push(decodeParameter(type, "0x" + readSlot(hex, i * 64)));
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
