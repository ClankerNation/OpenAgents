/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author
 * name: KHHH2312 Codex
 * date: 2026-05-31
 * @runtime documented in pull request metadata
 */

export type AbiType = string;

export interface AbiTypeDescriptor {
  type: string;
  components?: AbiTypeLike[];
  name?: string;
}

export type AbiTypeLike = AbiType | AbiTypeDescriptor;
export type DecodedAbiValue =
  | bigint
  | string
  | boolean
  | Buffer
  | DecodedAbiValue[];

export interface AbiParam {
  type: AbiTypeLike;
  value: string | number | bigint | boolean | Buffer | Uint8Array | unknown[];
}

interface RuntimePrimitive {
  kind: "primitive";
  type: string;
}

interface RuntimeTuple {
  kind: "tuple";
  components: RuntimeAbiType[];
}

interface RuntimeArray {
  kind: "array";
  base: RuntimeAbiType;
  length: number | null;
}

type RuntimeAbiType = RuntimePrimitive | RuntimeTuple | RuntimeArray;

const MAX_ABI_ARRAY_LENGTH = 100_000;
const MAX_SAFE_HEX_INDEX = Math.floor(Number.MAX_SAFE_INTEGER / 2);

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
  const cleaned = cleanHex(slot).padStart(64, "0");
  return BigInt("0x" + cleaned);
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return decodeUint256(slot) !== 0n;
}

export function decodeParameter(
  type: AbiTypeLike,
  data: string,
  byteOffset = 0,
): DecodedAbiValue {
  const runtimeType = parseAbiType(type);
  const hex = normalizeAbiData(data);
  return decodeAt(runtimeType, hex, byteOffset, 0);
}

export function decodeParams(
  types: AbiTypeLike[],
  data: string,
): DecodedAbiValue[] {
  const hex = normalizeAbiData(data);
  const runtimeTypes = types.map(parseAbiType);
  const values: DecodedAbiValue[] = [];
  let headOffset = 0;

  for (const runtimeType of runtimeTypes) {
    values.push(decodeAt(runtimeType, hex, headOffset, 0));
    headOffset = checkedAdd(
      headOffset,
      isDynamic(runtimeType) ? 32 : staticSizeBytes(runtimeType),
      "ABI parameter head offset",
    );
  }

  return values;
}

export const decodeParameters = decodeParams;

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}

function cleanHex(hex: string): string {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (cleaned.length > 0 && !/^[0-9a-fA-F]+$/.test(cleaned)) {
    throw new Error("Invalid ABI hex data");
  }
  return cleaned.length % 2 === 0 ? cleaned.toLowerCase() : `0${cleaned.toLowerCase()}`;
}

function normalizeAbiData(data: string): string {
  const hex = cleanHex(data);
  if (hex.length === 0) {
    throw new Error("ABI data is empty");
  }
  return hex.length < 64 ? hex.padStart(64, "0") : hex;
}

function readWord(hex: string, byteOffset: number): string {
  if (!Number.isInteger(byteOffset) || byteOffset < 0) {
    throw new Error("ABI byte offset must be a non-negative integer");
  }
  if (byteOffset > MAX_SAFE_HEX_INDEX) {
    throw new Error("ABI byte offset exceeds safe integer range");
  }

  if (byteOffset === 0 && hex.length < 64) {
    return hex.padStart(64, "0");
  }

  const start = byteOffset * 2;
  const end = checkedAdd(start, 64, "ABI word end");
  if (end > hex.length) {
    throw new Error("ABI word offset is out of bounds");
  }
  return hex.slice(start, end);
}

function readUintWord(hex: string, byteOffset: number): bigint {
  return BigInt(`0x${readWord(hex, byteOffset)}`);
}

function readUintOffset(hex: string, byteOffset: number): number {
  const value = readUintWord(hex, byteOffset);
  const maxSafe = BigInt(Number.MAX_SAFE_INTEGER);
  if (value > maxSafe) {
    throw new Error("ABI offset exceeds safe integer range");
  }
  return Number(value);
}

function readLength(hex: string, byteOffset: number): number {
  const value = readUintWord(hex, byteOffset);
  const maxSafe = BigInt(Number.MAX_SAFE_INTEGER);
  if (value > maxSafe) {
    throw new Error("ABI length exceeds safe integer range");
  }
  return Number(value);
}

function sliceBytes(hex: string, byteOffset: number, byteLength: number): string {
  if (byteOffset > MAX_SAFE_HEX_INDEX || byteLength > MAX_SAFE_HEX_INDEX) {
    throw new Error("ABI byte slice exceeds safe integer range");
  }
  const start = byteOffset * 2;
  const end = checkedAdd(
    start,
    checkedMultiply(byteLength, 2, "ABI byte slice length"),
    "ABI byte slice end",
  );
  if (end > hex.length) {
    throw new Error("ABI byte slice is out of bounds");
  }
  return hex.slice(start, end);
}

function parseAbiType(input: AbiTypeLike): RuntimeAbiType {
  if (typeof input === "string") {
    return parseAbiTypeString(input.trim());
  }

  if (input.type.startsWith("tuple")) {
    if (!input.components || input.components.length === 0) {
      throw new Error("Tuple ABI descriptor requires components");
    }

    const components = input.components.map(parseAbiType);
    let runtimeType: RuntimeAbiType = { kind: "tuple", components };
    for (const dimension of parseArrayDimensions(input.type.slice("tuple".length))) {
      runtimeType = { kind: "array", base: runtimeType, length: dimension };
    }
    return runtimeType;
  }

  return parseAbiTypeString(input.type.trim());
}

function parseAbiTypeString(type: string): RuntimeAbiType {
  const { baseType, dimensions } = splitArraySuffixes(type);
  let runtimeType: RuntimeAbiType;

  if (baseType.startsWith("(") && baseType.endsWith(")")) {
    const tupleBody = baseType.slice(1, -1);
    runtimeType = {
      kind: "tuple",
      components: splitTopLevel(tupleBody).map(parseAbiTypeString),
    };
  } else {
    runtimeType = { kind: "primitive", type: normalizePrimitive(baseType) };
  }

  for (const dimension of dimensions) {
    runtimeType = { kind: "array", base: runtimeType, length: dimension };
  }

  return runtimeType;
}

function splitArraySuffixes(type: string): {
  baseType: string;
  dimensions: Array<number | null>;
} {
  let baseType = type.trim();
  const dimensions: Array<number | null> = [];

  while (baseType.endsWith("]")) {
    const openBracket = baseType.lastIndexOf("[");
    if (openBracket === -1) {
      throw new Error(`Invalid ABI array type: ${type}`);
    }
    const rawLength = baseType.slice(openBracket + 1, -1);
    const dimension = parseStaticArrayLength(rawLength);
    dimensions.unshift(dimension);
    baseType = baseType.slice(0, openBracket).trim();
  }

  return { baseType, dimensions };
}

function parseArrayDimensions(suffix: string): Array<number | null> {
  if (suffix === "") {
    return [];
  }
  if (!/^(\[\d*\])+$/.test(suffix)) {
    throw new Error(`Invalid ABI tuple array suffix: ${suffix}`);
  }

  const dimensions: Array<number | null> = [];
  const matches = suffix.matchAll(/\[(\d*)\]/g);
  for (const match of matches) {
    dimensions.push(parseStaticArrayLength(match[1]));
  }
  return dimensions;
}

function parseStaticArrayLength(rawLength: string): number | null {
  if (rawLength === "") {
    return null;
  }
  if (!/^\d+$/.test(rawLength)) {
    throw new Error(`Invalid ABI array length: ${rawLength}`);
  }

  const length = BigInt(rawLength);
  if (length > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error("ABI array length exceeds safe integer range");
  }

  const numericLength = Number(length);
  assertSafeArrayLength(numericLength);
  return numericLength;
}

function normalizePrimitive(type: string): string {
  if (type === "uint") {
    return "uint256";
  }
  if (type === "int") {
    return "int256";
  }
  return type;
}

function splitTopLevel(input: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;

  for (let index = 0; index < input.length; index++) {
    const char = input[index];
    if (char === "(" || char === "[") {
      depth++;
    } else if (char === ")" || char === "]") {
      depth--;
      if (depth < 0) {
        throw new Error("Invalid ABI tuple type");
      }
    } else if (char === "," && depth === 0) {
      parts.push(input.slice(start, index).trim());
      start = index + 1;
    }
  }

  if (depth !== 0) {
    throw new Error("Invalid ABI tuple type");
  }

  const last = input.slice(start).trim();
  if (last.length > 0) {
    parts.push(last);
  }
  return parts;
}

function isDynamic(type: RuntimeAbiType): boolean {
  switch (type.kind) {
    case "primitive":
      return type.type === "string" || type.type === "bytes";
    case "array":
      return type.length === null || isDynamic(type.base);
    case "tuple":
      return type.components.some(isDynamic);
  }
}

function staticSizeBytes(type: RuntimeAbiType): number {
  if (isDynamic(type)) {
    return 32;
  }

  switch (type.kind) {
    case "primitive":
      return 32;
    case "array":
      if (type.length === null) {
        throw new Error("Dynamic arrays do not have a static size");
      }
      return checkedMultiply(
        type.length,
        staticSizeBytes(type.base),
        "ABI static array size",
      );
    case "tuple":
      return type.components.reduce(
        (sum, component) =>
          checkedAdd(sum, staticSizeBytes(component), "ABI static tuple size"),
        0,
      );
  }
}

function decodeAt(
  type: RuntimeAbiType,
  hex: string,
  headOffset: number,
  baseOffset: number,
): DecodedAbiValue {
  if (isDynamic(type)) {
    const relativeOffset = readUintOffset(hex, headOffset);
    return decodeDynamicPayload(type, hex, baseOffset + relativeOffset);
  }

  return decodeStatic(type, hex, headOffset, baseOffset);
}

function decodeStatic(
  type: RuntimeAbiType,
  hex: string,
  headOffset: number,
  baseOffset: number,
): DecodedAbiValue {
  switch (type.kind) {
    case "primitive":
      return decodePrimitive(type.type, hex, headOffset);
    case "array":
      if (type.length === null) {
        throw new Error("Dynamic arrays must be decoded from their payload");
      }
      return decodeArrayElements(type.base, type.length, hex, headOffset, headOffset);
    case "tuple":
      return decodeTuple(type.components, hex, headOffset, baseOffset);
  }
}

function decodeDynamicPayload(
  type: RuntimeAbiType,
  hex: string,
  dataOffset: number,
): DecodedAbiValue {
  if (type.kind === "primitive") {
    if (type.type === "string") {
      const length = readLength(hex, dataOffset);
      const raw = sliceBytes(
        hex,
        checkedAdd(dataOffset, 32, "ABI string payload offset"),
        length,
      );
      return Buffer.from(raw, "hex").toString("utf8");
    }

    if (type.type === "bytes") {
      const length = readLength(hex, dataOffset);
      const raw = sliceBytes(
        hex,
        checkedAdd(dataOffset, 32, "ABI bytes payload offset"),
        length,
      );
      return Buffer.from(raw, "hex");
    }
  }

  if (type.kind === "array") {
    if (type.length === null) {
      const length = readLength(hex, dataOffset);
      assertSafeArrayLength(length);
      const headOffset = checkedAdd(dataOffset, 32, "ABI dynamic array head offset");
      return decodeArrayElements(type.base, length, hex, headOffset, headOffset);
    }

    return decodeArrayElements(type.base, type.length, hex, dataOffset, dataOffset);
  }

  if (type.kind === "tuple") {
    return decodeTuple(type.components, hex, dataOffset, dataOffset);
  }

  throw new Error("ABI type is not dynamic");
}

function decodeArrayElements(
  elementType: RuntimeAbiType,
  length: number,
  hex: string,
  headOffset: number,
  baseOffset: number,
): DecodedAbiValue[] {
  assertSafeArrayLength(length);
  const values: DecodedAbiValue[] = [];
  const elementHeadSize = isDynamic(elementType) ? 32 : staticSizeBytes(elementType);

  for (let index = 0; index < length; index++) {
    const elementOffset = checkedAdd(
      headOffset,
      checkedMultiply(index, elementHeadSize, "ABI array element offset"),
      "ABI array element offset",
    );
    values.push(decodeAt(elementType, hex, elementOffset, baseOffset));
  }

  return values;
}

function decodeTuple(
  components: RuntimeAbiType[],
  hex: string,
  headOffset: number,
  baseOffset: number,
): DecodedAbiValue[] {
  const values: DecodedAbiValue[] = [];
  let componentOffset = headOffset;

  for (const component of components) {
    values.push(decodeAt(component, hex, componentOffset, baseOffset));
    componentOffset = checkedAdd(
      componentOffset,
      isDynamic(component) ? 32 : staticSizeBytes(component),
      "ABI tuple component offset",
    );
  }

  return values;
}

function decodePrimitive(
  type: string,
  hex: string,
  byteOffset: number,
): DecodedAbiValue {
  const word = readWord(hex, byteOffset);

  if (/^uint(8|16|24|32|40|48|56|64|72|80|88|96|104|112|120|128|136|144|152|160|168|176|184|192|200|208|216|224|232|240|248|256)$/.test(type)) {
    return BigInt(`0x${word}`);
  }

  if (/^int(8|16|24|32|40|48|56|64|72|80|88|96|104|112|120|128|136|144|152|160|168|176|184|192|200|208|216|224|232|240|248|256)$/.test(type)) {
    const bits = Number(type.slice(3));
    const value = BigInt(`0x${word}`);
    const signBit = 1n << BigInt(bits - 1);
    return (value & signBit) === 0n ? value : value - (1n << BigInt(bits));
  }

  if (type === "address") {
    return `0x${word.slice(-40).toLowerCase()}`;
  }

  if (type === "bool") {
    return BigInt(`0x${word}`) !== 0n;
  }

  const bytesMatch = type.match(/^bytes([1-9]|[12][0-9]|3[0-2])$/);
  if (bytesMatch) {
    const byteLength = Number(bytesMatch[1]);
    return `0x${word.slice(0, byteLength * 2)}`;
  }

  throw new Error(`Unsupported ABI type: ${type}`);
}

function assertSafeArrayLength(length: number): void {
  if (!Number.isInteger(length) || length < 0) {
    throw new Error("ABI array length must be a non-negative integer");
  }
  if (length > MAX_ABI_ARRAY_LENGTH) {
    throw new Error("ABI array length exceeds supported limit");
  }
}

function checkedAdd(left: number, right: number, context: string): number {
  if (!Number.isSafeInteger(left) || !Number.isSafeInteger(right)) {
    throw new Error(`${context} exceeds safe integer range`);
  }

  const result = left + right;
  if (!Number.isSafeInteger(result)) {
    throw new Error(`${context} exceeds safe integer range`);
  }
  return result;
}

function checkedMultiply(left: number, right: number, context: string): number {
  if (!Number.isSafeInteger(left) || !Number.isSafeInteger(right)) {
    throw new Error(`${context} exceeds safe integer range`);
  }

  const result = left * right;
  if (!Number.isSafeInteger(result)) {
    throw new Error(`${context} exceeds safe integer range`);
  }
  return result;
}
