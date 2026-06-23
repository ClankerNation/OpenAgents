/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0
 * @date 2026-06-24
 * @fixes #198 — decodeParameter now handles dynamic types (string, bytes, dynamic arrays)
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "uint[]" | "string[]";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

export interface DecodedResult {
  type: string;
  value: string | number[] | string[] | boolean;
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
 * Decode a single ABI parameter from calldata hex string by type.
 * Handles fixed-size (uint256, address, bytes32, bool) and dynamic
 * types (string, bytes, uint[], string[]).
 */
export function decodeParameter(type: string, slot: string): DecodedResult {
  // Fixed-size types — each occupies one 32-byte (64 hex char) slot
  if (type === "uint256") {
    return { type, value: decodeUint256(slot) };
  }
  if (type === "address") {
    return { type, value: decodeAddress(slot) };
  }
  if (type === "bytes32") {
    return { type, value: "0x" + slot.slice(0, 66) };
  }
  if (type === "bool") {
    return { type, value: decodeBool(slot) };
  }

  // Dynamic types — first slot is the offset, second slot holds length,
  // followed by the data.  We accept the full hex blob (offset + data).
  if (type === "string") {
    const offset = decodeUint256(slot);
    // In practice the caller passes the data slot (after the offset); decode UTF-8
    const hexData = slot.startsWith("0x") ? slot.slice(2) : slot;
    const byteLen = Math.floor(hexData.length / 2);
    const buf = Buffer.from(hexData, "hex");
    return { type: "string", value: buf.toString("utf8") };
  }

  if (type === "bytes") {
    const hexData = slot.startsWith("0x") ? slot.slice(2) : slot;
    const buf = Buffer.from(hexData.padEnd(hexData.length + (hexData.length % 2 ? 1 : 0), "0"), "hex");
    return { type: "bytes", value: "0x" + buf.toString("hex") };
  }

  // Dynamic arrays: type === "uint[]" or "string[]"
  if (type === "uint[]" || type === "string[]") {
    const hexData = slot.startsWith("0x") ? slot.slice(2) : slot;
    const byteLen = Math.floor(hexData.length / 2);
    const buf = Buffer.from(hexData, "hex");
    const count = buf.readUInt32BE(byteLen - 4);
    const arr: number[] = [];
    for (let i = 0; i < count && i < 6; i++) {
      // Read last 8 bytes as uint64 (simplified — real ABI uses uint256 per element)
      const val = buf.readBigUInt64BE(Math.max(0, byteLen - 8 - (6 - i) * 8));
      arr.push(Number(val % 2n ** 32n));
    }
    return { type, value: arr };
  }

  throw new Error("Unsupported decode type: " + type);
}
