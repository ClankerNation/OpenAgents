// @fix-author rafaio1
// @date 2026-08-25T00:30:00Z
// @runtime linux x64 /tmp/openagents_fix bash
// @platform-config Agentic bounty-hunter workflow
/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Refactored with SOLID principles and Object Calisthenics.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "tuple";

export interface AbiParam {
  type: AbiType;
  name?: string;
  value: string | number | bigint | boolean | Buffer | Uint8Array | AbiParam[];
  components?: AbiParam[];
}

const MAX_UINT256 = (1n << 256n) - 1n;

function normalizeHex(data: string): string {
  if (!data.startsWith("0x")) {
    throw new Error(`Expected 0x-prefixed hex string, got "${data}"`);
  }
  const cleaned = data.slice(2);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error(`Invalid hex characters in "${data}"`);
  }
  return cleaned || "0";
}

interface TypeDecoder {
  decode(data: string, param?: AbiParam): unknown;
}

class Uint256Decoder implements TypeDecoder {
  decode(data: string): bigint {
    const cleaned = normalizeHex(data);
    const padded = cleaned.padStart(64, "0");
    const value = BigInt("0x" + padded);
    if (value > MAX_UINT256) {
      throw new RangeError("Decoded value exceeds uint256 max");
    }
    return value;
  }
}

class AddressDecoder implements TypeDecoder {
  decode(data: string): string {
    const cleaned = normalizeHex(data);
    return "0x" + cleaned.slice(-40).padStart(40, "0");
  }
}

class BoolDecoder implements TypeDecoder {
  decode(data: string): boolean {
    return BigInt("0x" + normalizeHex(data)) !== 0n;
  }
}

class Bytes32Decoder implements TypeDecoder {
  decode(data: string): string {
    return "0x" + normalizeHex(data).padStart(64, "0");
  }
}

class StringDecoder implements TypeDecoder {
  decode(data: string): string {
    const cleaned = normalizeHex(data);
    this.validateBounds(cleaned, 64);
    const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
    this.validateBounds(cleaned, offset + 64);
    const length = parseInt(cleaned.slice(offset, offset + 64), 16);
    const strStart = offset + 64;
    const strEnd = strStart + length * 2;
    this.validateBounds(cleaned, strEnd);
    const hexStr = cleaned.slice(strStart, strEnd);
    return Buffer.from(hexStr, "hex").toString("utf-8");
  }

  private validateBounds(data: string, index: number): void {
    if (index > data.length || isNaN(index)) {
      throw new RangeError(`ABI data out of bounds at index ${index}`);
    }
  }
}

class BytesDecoder implements TypeDecoder {
  decode(data: string): Buffer {
    const cleaned = normalizeHex(data);
    const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
    const length = parseInt(cleaned.slice(offset, offset + 64), 16);
    const bytesStart = offset + 64;
    const bytesEnd = bytesStart + length * 2;
    if (bytesEnd > cleaned.length) {
      throw new RangeError("Bytes data exceeds available buffer");
    }
    const hexBytes = cleaned.slice(bytesStart, bytesEnd);
    return Buffer.from(hexBytes, "hex");
  }
}

class ArrayDecoder implements TypeDecoder {
  constructor(private registry: Map<string, TypeDecoder>) {}

  decode(data: string, param?: AbiParam): unknown[] {
    if (!param) throw new Error("Array decoding requires element type");
    const elementType = param.type.replace("[]", "") as AbiType;
    const decoder = this.registry.get(elementType);
    if (!decoder) throw new Error(`No decoder registered for type: ${elementType}`);

    const cleaned = normalizeHex(data);
    const offset = parseInt(cleaned.slice(0, 64), 16) * 2;
    const length = parseInt(cleaned.slice(offset, offset + 64), 16);
    const result: unknown[] = [];
    let pos = offset + 64;
    
    for (let i = 0; i < length; i++) {
      const slot = "0x" + cleaned.slice(pos, pos + 64);
      result.push(decoder.decode(slot));
      pos += 64;
    }
    return result;
  }
}

class TupleDecoder implements TypeDecoder {
  constructor(private registry: Map<string, TypeDecoder>) {}

  decode(data: string, param?: AbiParam): Record<string, unknown> {
    if (!param?.components) throw new Error("Tuple decoding requires components");
    const cleaned = normalizeHex(data);
    const result: Record<string, unknown> = {};
    let pos = 0;
    
    for (const comp of param.components) {
      const slot = "0x" + cleaned.slice(pos, pos + 64);
      const fieldName = comp.name ?? `field_${pos}`;
      const decoder = this.registry.get(comp.type);
      
      if (!decoder) {
        throw new Error(`No decoder registered for tuple field type: ${comp.type}`);
      }
      
      result[fieldName] = decoder.decode(slot, comp);
      pos += 64;
    }
    return result;
  }
}

const DECODER_REGISTRY = new Map<string, TypeDecoder>();
const uint256Decoder = new Uint256Decoder();
DECODER_REGISTRY.set("uint256", uint256Decoder);
DECODER_REGISTRY.set("address", new AddressDecoder());
DECODER_REGISTRY.set("bool", new BoolDecoder());
DECODER_REGISTRY.set("bytes32", new Bytes32Decoder());
DECODER_REGISTRY.set("string", new StringDecoder());
DECODER_REGISTRY.set("bytes", new BytesDecoder());
DECODER_REGISTRY.set("array", new ArrayDecoder(DECODER_REGISTRY));
DECODER_REGISTRY.set("tuple", new TupleDecoder(DECODER_REGISTRY));

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new RangeError(`encodeUint256: value out of range [0, 2^256-1]: ${n}`);
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeParams(params: AbiParam[]): string {
  let encoded = "";
  for (const param of params) {
    switch (param.type) {
      case "uint256":
        encoded += encodeUint256(param.value as bigint | number);
        break;
      case "address":
        encoded += (param.value as string).replace("0x", "").padStart(64, "0");
        break;
      case "bool":
        encoded += (param.value ? "1" : "0").padStart(64, "0");
        break;
      case "string": {
        const strBytes = Buffer.from(param.value as string, "utf-8");
        const hexStr = strBytes.toString("hex");
        const lenHex = BigInt(strBytes.length).toString(16).padStart(64, "0");
        encoded += lenHex + hexStr.padEnd(Math.ceil(hexStr.length / 64) * 64, "0");
        break;
      }
    }
  }
  return encoded;
}

export function decodeParameter(type: AbiType, data: string, param?: AbiParam): unknown {
  const decoder = DECODER_REGISTRY.get(type);
  if (!decoder) {
    throw new Error(`Unsupported ABI type: ${type}`);
  }
  return decoder.decode(data, param);
}

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}
