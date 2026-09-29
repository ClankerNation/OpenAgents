/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author doubao-agent (spiritwanghs fork), 2026-09-29
 * @preamble Autonomous coding agent executing GitHub bounties; user provides a fine-grained GitHub PAT and asks to push fixes directly.
 * @runtime os=linux arch=x64 working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=bash
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

// ---- ABI decoding for contract return values ----

const SLOT = 32;

function isDynamic(type: string): boolean {
  return (
    type === "string" ||
    type === "bytes" ||
    type.endsWith("[]") ||
    type.startsWith("(")
  );
}

function headSlots(type: string): number {
  if (type === "tuple" || type.startsWith("(")) return 1;
  if (type.endsWith("[]")) return 1;
  return 1;
}

function readOffset(slot: Buffer): number {
  return Number(BigInt("0x" + slot.toString("hex")));
}

function readLength(data: Buffer, off: number): number {
  // length is the last 32 bytes at `off`
  return Number(data.readBigUInt64BE(off + SLOT - 8));
}

function decodeFixed(slot: Buffer, type: string): any {
  if (type === "uint256" || type === "uint") {
    return BigInt("0x" + slot.toString("hex"));
  }
  if (type === "address") {
    return "0x" + slot.slice(12).toString("hex").toLowerCase();
  }
  if (type === "bool") {
    return slot[31] !== 0;
  }
  if (type === "bytes32") {
    return "0x" + slot.toString("hex");
  }
  throw new Error("decodeFixed: unknown fixed type " + type);
}

function decodeAt(data: Buffer, off: number, type: string): any {
  if (!isDynamic(type)) {
    return decodeFixed(data.slice(off, off + SLOT), type);
  }
  // dynamic: the head slot at `off` is an offset
  const dynOff = readOffset(data.slice(off, off + SLOT));

  if (type === "string") {
    const len = readLength(data, dynOff);
    return data.slice(dynOff + SLOT, dynOff + SLOT + len).toString("utf8");
  }
  if (type === "bytes") {
    const len = readLength(data, dynOff);
    return data.slice(dynOff + SLOT, dynOff + SLOT + len);
  }
  const arrMatch = type.match(/^(.+)\[\]$/);
  if (arrMatch) {
    const elemType = arrMatch[1];
    const len = readLength(data, dynOff);
    const out: any[] = [];
    let p = dynOff + SLOT;
    for (let i = 0; i < len; i++) {
      out.push(decodeAt(data, p, elemType));
      p += isDynamic(elemType) ? SLOT : SLOT;
    }
    return out;
  }
  // tuple: (t1,t2,...) — treat like a struct; members follow at dynOff
  if (type.startsWith("(")) {
    const inner = type.slice(1, -1);
    const members = inner.split(",");
    const out: any[] = [];
    let p = dynOff;
    // First pass: collect head slots for members
    const headPts: number[] = [];
    for (const m of members) {
      headPts.push(p);
      p += SLOT;
    }
    for (let i = 0; i < members.length; i++) {
      out.push(decodeAt(data, headPts[i], members[i]));
    }
    return out;
  }
  throw new Error("decodeAt: unsupported type " + type);
}

/**
 * Decode ABI-encoded contract return data into JS values.
 *
 * @param data  hex string (with or without 0x) of the return bytes
 * @param types list of Solidity types, e.g. ["uint256","string","address[]"]
 */
export function decodeParameter(data: string, types: string[]): any[] {
  const clean = data.startsWith("0x") ? data.slice(2) : data;
  const buf = Buffer.from(clean, "hex");
  const out: any[] = [];
  let off = 0;
  for (const t of types) {
    out.push(decodeAt(buf, off, t));
    off += SLOT;
  }
  return out;
}
