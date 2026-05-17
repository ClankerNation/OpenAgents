@fix-author hermes-agent-deepseek-v4-pro
@date 2026-05-17T23:00:00Z
@init-context User goal: Generate $5+ from GitHub bounties. Session configured for Feishu messaging. Using GitHub PAT token with full repo access. Connected platforms: local, feishu.
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/root/hermes-agent, shell=bash
/**
 * ABI encoding/decoding utilities. Supports fixed + dynamic types (string, bytes, arrays), nested tuples.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";
export interface AbiParam { type: AbiType; value: string | number | bigint | boolean; }

export function encodeUint256(value: bigint | number): string { return BigInt(value).toString(16).padStart(64, "0"); }
export function encodeAddress(address: string): string { return (address.startsWith("0x") ? address.slice(2) : address).toLowerCase().padStart(64, "0"); }
export function encodeBytes32(data: string): string { return (data.startsWith("0x") ? data.slice(2) : data).padEnd(64, "0"); }
export function encodeBool(value: boolean): string { return value ? "1".padStart(64, "0") : "0".padStart(64, "0"); }

export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf8").toString("hex");
  return value.length.toString(16).padStart(64, "0") + hex.padEnd(64, "0");
}

export function encodeParams(params: AbiParam[]): string {
  let e = "0x";
  for (const p of params) {
    switch (p.type) {
      case "uint256": e += encodeUint256(BigInt(p.value as number)); break;
      case "address": e += encodeAddress(p.value as string); break;
      case "bytes32": e += encodeBytes32(p.value as string); break;
      case "bool": e += encodeBool(p.value as boolean); break;
      case "string": e += encodeString(p.value as string); break;
    }
  }
  return e;
}

export function decodeHex(hex: string): bigint { return BigInt("0x" + (hex.startsWith("0x") ? hex.slice(2) : hex)); }
export function decodeUint256(slot: string): bigint { return BigInt("0x" + (slot.startsWith("0x") ? slot.slice(2) : slot).padStart(64, "0")); }
export function decodeAddress(slot: string): string { return "0x" + slot.slice(-40).toLowerCase(); }
export function decodeBool(slot: string): boolean { return BigInt("0x" + (slot.startsWith("0x") ? slot.slice(2) : slot)) !== 0n; }

export function decodeString(data: string, offset: number): { value: string; consumed: number } {
  const c = data.startsWith("0x") ? data.slice(2) : data;
  const len = Number(BigInt("0x" + c.slice(offset * 2, offset * 2 + 64)));
  const bytes = Buffer.from(c.slice(offset * 2 + 64, offset * 2 + 64 + len * 2), "hex");
  return { value: bytes.toString("utf8"), consumed: offset + 32 + Math.ceil(len / 32) * 32 };
}

export function decodeBytes(data: string, offset: number): { value: Uint8Array; consumed: number } {
  const c = data.startsWith("0x") ? data.slice(2) : data;
  const len = Number(BigInt("0x" + c.slice(offset * 2, offset * 2 + 64)));
  const bytes = Buffer.from(c.slice(offset * 2 + 64, offset * 2 + 64 + len * 2), "hex");
  return { value: new Uint8Array(bytes), consumed: offset + 32 + Math.ceil(len / 32) * 32 };
}

export function decodeArray(data: string, offset: number, elementType: string): { value: any[]; consumed: number } {
  const c = data.startsWith("0x") ? data.slice(2) : data;
  const len = Number(BigInt("0x" + c.slice(offset * 2, offset * 2 + 64)));
  const elements: any[] = [];
  let pos = offset + 32;
  for (let i = 0; i < len; i++) { const d = decodeParameter(data, pos, elementType); elements.push(d.value); pos = d.nextOffset; }
  return { value: elements, consumed: pos };
}

export function decodeTuple(data: string, offset: number, types: string[]): { value: any[]; consumed: number } {
  const vals: any[] = []; let pos = offset;
  for (const t of types) { const d = decodeParameter(data, pos, t); vals.push(d.value); pos = d.nextOffset; }
  return { value: vals, consumed: pos };
}

export function decodeParameter(data: string, offset: number, type: string): { value: any; nextOffset: number } {
  if (type.endsWith("[]")) { const d = decodeArray(data, offset, type.slice(0, -2)); return { value: d.value, nextOffset: d.consumed }; }
  if (type.startsWith("(") && type.endsWith(")")) { const d = decodeTuple(data, offset, type.slice(1, -1).split(",").map(t=>t.trim())); return { value: d.value, nextOffset: d.consumed }; }
  const c = data.startsWith("0x") ? data.slice(2) : data;
  const slot = c.slice(offset * 2, offset * 2 + 64);
  const uints = ["uint8","uint16","uint32","uint64","uint128","uint256"];
  if (uints.includes(type)) return { value: decodeUint256(slot), nextOffset: offset + 32 };
  if (type === "address") return { value: decodeAddress(slot), nextOffset: offset + 32 };
  if (type === "bool") return { value: decodeBool(slot), nextOffset: offset + 32 };
  if (type === "bytes32") return { value: "0x" + slot, nextOffset: offset + 32 };
  if (type === "string") { const ref = Number(decodeUint256(slot)) / 32; const d = decodeString(data, ref); return { value: d.value, nextOffset: offset + 32 }; }
  if (type === "bytes") { const ref = Number(decodeUint256(slot)) / 32; const d = decodeBytes(data, ref); return { value: d.value, nextOffset: offset + 32 }; }
  throw new Error("Unsupported type: " + type);
}

export function functionSelector(sig: string): string { const h = require("crypto").createHash("sha3-256").update(sig).digest("hex"); return "0x" + h.slice(0, 8); }
export function packCalldata(selector: string, params: AbiParam[]): string { return selector + encodeParams(params).slice(2); }
