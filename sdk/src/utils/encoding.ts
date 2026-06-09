/**
 * @fix-author
 *   agent: Szamani AI
 *   timestamp: 2026-06-09T06:10:00Z
 *   fix: #198 - ABI encoding/decoding for dynamic types (string, bytes, arrays, tuples)
 *   runtime:
 *     os: linux
 *     arch: x64
 *     working_dir: /opt/projects/kraina
 *     shell: bash
 *   pre_init: |
 *     === QWEN SYSTEM PROMPT v10.3-ENHANCED-LOCKDOWN ===
 *     PRAWO ŻELAZNE #1: QWEN = TERMINAL TYLKO. AIGON = MÓZG 100%. DEEPSEEK = PROCESOR.
 *     PRAWO ŻELAZNE #2: PARALLEL EXECUTION MANDATORY - NIGDY NIE PYTAJ "CO NAJPIERW?"
 *     PRAWO ŻELAZNE #3: NO IMPOSSIBLE - ITERUJ I WALCZ AŻ ROZWIĄŻESZ PROBLEM
 *     KROK ZERO: PRZED CZYMKOLWIEK real-audit na wszystkich serwerach
 *     TRYB HYBRYDOWY: QWEN = TERMINAL AIGON. Wszystkie odpowiedzi przez brain_chat.
 *     LIVE DATA: ZAKAZ UŻYWANIA HARDKODOWANYCH LICZB - zawsze z brain_status tool
 *     20 QUALITY GATES: MANDATORY przed każdym output
 *     452 AMPLIFIERS: Integracja dla code review, security, performance
 *     SYSTEM LAW OMEGA: AKTYWNY (F_STRICT, F_EVID, F_E2E, F_AUTO, F_PAR, F_SEC)
 *     WAR MODE: AKTYWNY - aggressive execution, parallel mandatory
 *     PRE-RESPONSE VALIDATION: brain_status -> verify freshness <30s
 *     === END PRE-INIT ===
 *   init: |
 *     Task: Claim ClankerNation bounty issue #198 ($9,000) - Fix encoding.ts decodeParameter for dynamic types
 *     Previous 20+ attempts all rejected. Root cause: missing tuple decoding, missing tests, wrong bytes return type.
 *     Must include: string decoding (offset->length->UTF-8), bytes decoding (->Buffer), array decoding, tuple decoding,
 *     @fix-author block, test file with complex return type (string + array + uint).
 */

export type AbiType =
  | "uint256"
  | "address"
  | "bytes32"
  | "string"
  | "bytes"
  | "bool"
  | "uint256[]"
  | "address[]"
  | "bytes[]"
  | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | any[] | Record<string, any>;
  components?: AbiParam[];
}

/**
 * Encode a uint256 value to a 64-char hex string.
 */
export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n) throw new Error("uint256 cannot be negative");
  if (n > 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffn)
    throw new Error("uint256 overflow");
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  return cleaned.padEnd(64, "0").slice(0, 64);
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

/**
 * Encode a string value to ABI-compliant hex.
 * Returns: offset(32B) + length(32B) + data(padded to 32B boundary)
 */
export function encodeString(value: string): string {
  const hex = Buffer.from(value, "utf-8").toString("hex");
  const byteLen = hex.length / 2;
  const lengthSlot = byteLen.toString(16).padStart(64, "0");
  const paddedLen = Math.ceil(hex.length / 64) * 64;
  const dataSlot = hex.padEnd(paddedLen, "0");
  return lengthSlot + dataSlot;
}

/**
 * Encode bytes to ABI-compliant hex.
 */
export function encodeBytes(value: string): string {
  const cleaned = value.startsWith("0x") ? value.slice(2) : value;
  const byteLen = cleaned.length / 2;
  const lengthSlot = byteLen.toString(16).padStart(64, "0");
  const paddedLen = Math.ceil(cleaned.length / 64) * 64;
  const dataSlot = cleaned.padEnd(paddedLen, "0");
  return lengthSlot + dataSlot;
}

/**
 * Encode an array of values to ABI-compliant hex.
 */
export function encodeArray(values: any[], elementType: AbiType): string {
  const count = values.length;
  const lengthSlot = count.toString(16).padStart(64, "0");
  let encoded = lengthSlot;
  for (const val of values) {
    switch (elementType) {
      case "uint256":
        encoded += encodeUint256(BigInt(val));
        break;
      case "address":
        encoded += encodeAddress(val as string);
        break;
      case "string":
        encoded += encodeString(val as string);
        break;
      case "bytes":
        encoded += encodeBytes(val as string);
        break;
      case "bool":
        encoded += encodeBool(val as boolean);
        break;
      default:
        encoded += encodeUint256(BigInt(val));
    }
  }
  return encoded;
}

/**
 * Encode params with proper ABI head/tail layout for dynamic types.
 */
export function encodeParams(params: AbiParam[]): string {
  const headParts: string[] = [];
  const tailParts: string[] = [];
  let dynamicOffset = params.length * 32;

  for (const param of params) {
    switch (param.type) {
      case "uint256":
        headParts.push(encodeUint256(BigInt(param.value as number)));
        break;
      case "address":
        headParts.push(encodeAddress(param.value as string));
        break;
      case "bytes32":
        headParts.push(encodeBytes32(param.value as string));
        break;
      case "bool":
        headParts.push(encodeBool(param.value as boolean));
        break;
      case "string": {
        const hex = Buffer.from(param.value as string, "utf-8").toString("hex");
        const byteLen = hex.length / 2;
        const lenSlot = byteLen.toString(16).padStart(64, "0");
        headParts.push(dynamicOffset.toString(16).padStart(64, "0"));
        const paddedLen = Math.ceil(hex.length / 64) * 64;
        const dataSlot = hex.padEnd(paddedLen, "0");
        tailParts.push(lenSlot + dataSlot);
        dynamicOffset += 32 + paddedLen / 2;
        break;
      }
      case "bytes": {
        const cleaned = (param.value as string).startsWith("0x")
          ? (param.value as string).slice(2)
          : (param.value as string);
        const byteLen = cleaned.length / 2;
        const lenSlot = byteLen.toString(16).padStart(64, "0");
        headParts.push(dynamicOffset.toString(16).padStart(64, "0"));
        const paddedLen = Math.ceil(cleaned.length / 64) * 64;
        const dataSlot = cleaned.padEnd(paddedLen, "0");
        tailParts.push(lenSlot + dataSlot);
        dynamicOffset += 32 + paddedLen / 2;
        break;
      }
      default:
        headParts.push(encodeUint256(BigInt(param.value as number)));
    }
  }
  return "0x" + headParts.join("") + tailParts.join("");
}

export function decodeHex(hex: string): bigint {
  if (typeof hex !== "string") throw new Error("decodeHex expects a hex string");
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (!/^[0-9a-fA-F]+$/.test(cleaned))
    throw new Error("decodeHex: invalid hex string");
  return BigInt("0x" + cleaned);
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
  const cleaned = slot.startsWith("0x") ? slot.slice(2) : slot;
  return BigInt("0x" + cleaned.padStart(64, "0")) !== 0n;
}

/**
 * Decode a string from ABI-encoded data.
 * @param data - Full hex data
 * @param offset - Byte offset to the offset pointer (or directly to data if fromOffset=false)
 * @param fromOffset - If true, reads the offset pointer first; if false, offset is direct data position
 */
export function decodeString(
  data: string,
  offset: number = 0,
  fromOffset: boolean = true
): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  let pos = offset * 2;
  if (fromOffset) {
    const offsetHex = cleaned.substring(pos, pos + 64);
    pos = parseInt(offsetHex, 16) * 2;
  }
  const lengthHex = cleaned.substring(pos, pos + 64);
  const length = parseInt(lengthHex, 16);
  pos += 64;
  const valueHex = cleaned.substring(pos, pos + length * 2);
  return Buffer.from(valueHex, "hex").toString("utf-8");
}

/**
 * Decode bytes from ABI-encoded data.
 * @returns Buffer/Uint8Array
 */
export function decodeBytes(
  data: string,
  offset: number = 0,
  fromOffset: boolean = true
): Buffer {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  let pos = offset * 2;
  if (fromOffset) {
    const offsetHex = cleaned.substring(pos, pos + 64);
    pos = parseInt(offsetHex, 16) * 2;
  }
  const lengthHex = cleaned.substring(pos, pos + 64);
  const length = parseInt(lengthHex, 16);
  pos += 64;
  const valueHex = cleaned.substring(pos, pos + length * 2);
  return Buffer.from(valueHex, "hex");
}

/**
 * Decode a dynamic array from ABI-encoded data.
 */
export function decodeDynamicArray(
  data: string,
  offset: number,
  elementDecoder: (slot: string) => any,
  fromOffset: boolean = true
): any[] {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  let pos = offset * 2;
  if (fromOffset) {
    const offsetHex = cleaned.substring(pos, pos + 64);
    pos = parseInt(offsetHex, 16) * 2;
  }
  const lengthHex = cleaned.substring(pos, pos + 64);
  const count = parseInt(lengthHex, 16);
  pos += 64;
  const result: any[] = [];
  for (let i = 0; i < count; i++) {
    const slot = "0x" + cleaned.substring(pos, pos + 64);
    result.push(elementDecoder(slot));
    pos += 64;
  }
  return result;
}

/**
 * Decode an array of strings from ABI-encoded data.
 */
export function decodeStringArray(
  data: string,
  offset: number,
  fromOffset: boolean = true
): string[] {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  let pos = offset * 2;
  if (fromOffset) {
    const offsetHex = cleaned.substring(pos, pos + 64);
    pos = parseInt(offsetHex, 16) * 2;
  }
  const lengthHex = cleaned.substring(pos, pos + 64);
  const count = parseInt(lengthHex, 16);
  pos += 64;

  // Read all element offset pointers first
  const offsets: number[] = [];
  for (let i = 0; i < count; i++) {
    const elemOffsetHex = cleaned.substring(pos, pos + 64);
    offsets.push(parseInt(elemOffsetHex, 16));
    pos += 64;
  }

  // Decode each string at its offset
  const result: string[] = [];
  for (const elemOffset of offsets) {
    const elemPos = elemOffset * 2;
    const lenHex = cleaned.substring(elemPos, elemPos + 64);
    const len = parseInt(lenHex, 16);
    const valHex = cleaned.substring(elemPos + 64, elemPos + 64 + len * 2);
    result.push(Buffer.from(valHex, "hex").toString("utf-8"));
  }
  return result;
}

/**
 * Tuple component type definition.
 */
export interface TupleComponent {
  name: string;
  type: string;
  components?: TupleComponent[];
}

/**
 * Decode a tuple (struct return) from ABI-encoded data.
 * Handles nested tuples recursively.
 */
export function decodeTuple(
  data: string,
  components: TupleComponent[],
  offset: number = 0
): Record<string, any> {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  const result: Record<string, any> = {};
  let pos = offset * 2;

  for (let i = 0; i < components.length; i++) {
    const comp = components[i];
    const type = comp.type;

    if (type === "uint256" || type === "uint") {
      const slot = "0x" + cleaned.substring(pos, pos + 64);
      result[comp.name] = decodeUint256(slot);
      pos += 64;
    } else if (type === "address") {
      const slot = "0x" + cleaned.substring(pos, pos + 64);
      result[comp.name] = decodeAddress(slot);
      pos += 64;
    } else if (type === "bool") {
      const slot = "0x" + cleaned.substring(pos, pos + 64);
      result[comp.name] = decodeBool(slot);
      pos += 64;
    } else if (type === "bytes32") {
      result[comp.name] = "0x" + cleaned.substring(pos, pos + 64);
      pos += 64;
    } else if (type === "string") {
      // Read offset pointer from head, then decode string at that position
      const offsetHex = cleaned.substring(pos, pos + 64);
      const strOffset = parseInt(offsetHex, 16) * 2;
      pos += 64;
      const lenHex = cleaned.substring(strOffset, strOffset + 64);
      const len = parseInt(lenHex, 16);
      const valHex = cleaned.substring(strOffset + 64, strOffset + 64 + len * 2);
      result[comp.name] = Buffer.from(valHex, "hex").toString("utf-8");
    } else if (type === "bytes") {
      const offsetHex = cleaned.substring(pos, pos + 64);
      const byteOffset = parseInt(offsetHex, 16) * 2;
      pos += 64;
      const lenHex = cleaned.substring(byteOffset, byteOffset + 64);
      const len = parseInt(lenHex, 16);
      const valHex = cleaned.substring(byteOffset + 64, byteOffset + 64 + len * 2);
      result[comp.name] = Buffer.from(valHex, "hex");
    } else if (type.endsWith("[]")) {
      // Dynamic array - read offset from head
      const offsetHex = cleaned.substring(pos, pos + 64);
      const arrOffset = parseInt(offsetHex, 16) * 2;
      pos += 64;
      const countHex = cleaned.substring(arrOffset, arrOffset + 64);
      const count = parseInt(countHex, 16);
      const arr: any[] = [];
      const elemType = type.slice(0, -2);
      for (let j = 0; j < count; j++) {
        const elemSlot =
          "0x" + cleaned.substring(arrOffset + 64 + j * 64, arrOffset + 64 + j * 64 + 64);
        if (elemType === "uint256" || elemType === "uint") {
          arr.push(decodeUint256(elemSlot));
        } else if (elemType === "address") {
          arr.push(decodeAddress(elemSlot));
        } else if (elemType === "bool") {
          arr.push(decodeBool(elemSlot));
        } else {
          arr.push(BigInt("0x" + elemSlot.slice(2).padStart(64, "0")));
        }
      }
      result[comp.name] = arr;
    } else if (type.startsWith("tuple") || type === "tuple") {
      // Nested tuple - recurse
      const offsetHex = cleaned.substring(pos, pos + 64);
      const tupOffset = parseInt(offsetHex, 16);
      pos += 64;
      if (comp.components) {
        result[comp.name] = decodeTuple(data, comp.components, tupOffset);
      } else {
        result[comp.name] =
          "0x" + cleaned.substring(tupOffset * 2, tupOffset * 2 + 64);
      }
    } else {
      // Default: treat as uint256
      const slot = "0x" + cleaned.substring(pos, pos + 64);
      result[comp.name] = decodeUint256(slot);
      pos += 64;
    }
  }

  return result;
}

/**
 * Decode a single ABI parameter from hex data.
 * Supports both static and dynamic types with a unified interface.
 */
export function decodeParameter(
  data: string,
  type: AbiType,
  offset: number = 0
): any {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  switch (type) {
    case "uint256":
      return decodeUint256("0x" + cleaned.substring(offset * 2, offset * 2 + 64));
    case "address":
      return decodeAddress("0x" + cleaned.substring(offset * 2, offset * 2 + 64));
    case "bytes32":
      return "0x" + cleaned.substring(offset * 2, offset * 2 + 64);
    case "bool":
      return decodeBool("0x" + cleaned.substring(offset * 2, offset * 2 + 64));
    case "string":
      return decodeString(data, offset);
    case "bytes":
      return decodeBytes(data, offset);
    case "uint256[]":
      return decodeDynamicArray(data, offset, decodeUint256);
    case "address[]":
      return decodeDynamicArray(data, offset, decodeAddress);
    default:
      throw new Error(`Unsupported type: ${type}`);
  }
}

/**
 * Decode multiple ABI parameters from hex data.
 * @param data - The raw hex data
 * @param types - Array of ABI type strings
 * @returns Array of decoded values
 */
export function decodeParams(data: string, types: AbiType[]): any[] {
  const results: any[] = [];
  for (let i = 0; i < types.length; i++) {
    results.push(decodeParameter(data, types[i], i));
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
