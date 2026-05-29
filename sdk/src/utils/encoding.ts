/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType =
  | "uint256"
  | "address"
  | "bytes32"
  | "string"
  | "bytes"
  | "bool"
  | "tuple"
  | `${string}[]`;

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
  components?: AbiTypeDescriptor[];
}

export interface AbiTypeDescriptor {
  type: AbiType;
  components?: AbiTypeDescriptor[];
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

function stripHexPrefix(hex: string): string {
  return hex.startsWith("0x") ? hex.slice(2) : hex;
}

function readWord(data: string, byteOffset: number): string {
  const hex = stripHexPrefix(data);
  const start = byteOffset * 2;
  return hex.slice(start, start + 64).padStart(64, "0");
}

function readUint(data: string, byteOffset: number): bigint {
  return BigInt("0x" + readWord(data, byteOffset));
}

function normalizeDescriptor(type: AbiType | AbiTypeDescriptor): AbiTypeDescriptor {
  return typeof type === "string" ? { type } : type;
}

function isDynamicType(type: AbiTypeDescriptor): boolean {
  if (type.type === "string" || type.type === "bytes" || type.type.endsWith("[]")) {
    return true;
  }
  if (type.type === "tuple") {
    return type.components?.some(isDynamicType) ?? false;
  }
  return false;
}

function decodeStatic(type: AbiTypeDescriptor, data: string, byteOffset: number): unknown {
  const word = readWord(data, byteOffset);

  switch (type.type) {
    case "uint256":
      return BigInt("0x" + word);
    case "address":
      return "0x" + word.slice(24).toLowerCase();
    case "bytes32":
      return "0x" + word;
    case "bool":
      return BigInt("0x" + word) !== 0n;
    case "tuple":
      return decodeTuple(type, data, byteOffset, byteOffset);
    default:
      throw new Error(`Unsupported static ABI type: ${type.type}`);
  }
}

function decodeBytesAt(data: string, byteOffset: number): Buffer {
  const hex = stripHexPrefix(data);
  const length = Number(readUint(data, byteOffset));
  const start = (byteOffset + 32) * 2;
  return Buffer.from(hex.slice(start, start + length * 2), "hex");
}

function decodeArray(type: AbiTypeDescriptor, data: string, slotOffset: number, baseOffset: number): unknown[] {
  const elementType = type.type.slice(0, -2) as AbiType;
  const elementDescriptor: AbiTypeDescriptor =
    elementType === "tuple"
      ? { type: elementType, components: type.components }
      : { type: elementType };
  const arrayOffset = Number(readUint(data, slotOffset));
  const arrayStart = baseOffset + arrayOffset;
  const length = Number(readUint(data, arrayStart));
  const values: unknown[] = [];

  for (let i = 0; i < length; i++) {
    const elementSlot = arrayStart + 32 + i * 32;
    values.push(decodeType(elementDescriptor, data, elementSlot, arrayStart));
  }

  return values;
}

function decodeTuple(type: AbiTypeDescriptor, data: string, slotOffset: number, baseOffset: number): unknown[] {
  const components = type.components ?? [];
  const tupleStart = isDynamicType(type) ? baseOffset + Number(readUint(data, slotOffset)) : slotOffset;

  return components.map((component, index) =>
    decodeType(component, data, tupleStart + index * 32, tupleStart)
  );
}

function decodeType(type: AbiTypeDescriptor, data: string, slotOffset: number, baseOffset: number): unknown {
  if (!isDynamicType(type)) {
    return decodeStatic(type, data, slotOffset);
  }

  if (type.type === "string") {
    return decodeBytesAt(data, baseOffset + Number(readUint(data, slotOffset))).toString("utf8");
  }

  if (type.type === "bytes") {
    return decodeBytesAt(data, baseOffset + Number(readUint(data, slotOffset)));
  }

  if (type.type.endsWith("[]")) {
    return decodeArray(type, data, slotOffset, baseOffset);
  }

  if (type.type === "tuple") {
    return decodeTuple(type, data, slotOffset, baseOffset);
  }

  throw new Error(`Unsupported ABI type: ${type.type}`);
}

export function decodeParameter(type: AbiType | AbiTypeDescriptor, data: string): unknown {
  const descriptor = normalizeDescriptor(type);
  if (descriptor.type === "tuple" && isDynamicType(descriptor)) {
    const hexLength = stripHexPrefix(data).length / 2;
    const possibleOffset = Number(readUint(data, 0));
    if (possibleOffset < hexLength && possibleOffset % 32 === 0) {
      return decodeType(descriptor, data, 0, 0);
    }
    return decodeTuple(descriptor, data, 0, 0);
  }
  return decodeType(descriptor, data, 0, 0);
}

export function decodeParams(types: Array<AbiType | AbiTypeDescriptor>, data: string): unknown[] {
  return types.map((type, index) => decodeType(normalizeDescriptor(type), data, index * 32, 0));
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
