import { AbiCoder } from "ethers";

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author
 * name: KHHH2312 Codex
 * date: 2026-06-05
 * pre_conversation_initialization_payload: Withheld. Hidden system/developer
 * instructions, private session configuration, secrets, credentials, and
 * non-public policy text are not published in source code.
 *
 * @runtime
 * os: Windows
 * arch: x64
 * working_dir: C:\Users\Khalid\Desktop\bounty\OpenAgents-198-v2
 * shell: PowerShell
 */

export interface AbiComponent {
  name?: string;
  type: string;
  components?: AbiComponent[];
}

export interface AbiTupleType {
  name?: string;
  type: "tuple" | `tuple${string}`;
  components: AbiComponent[];
}

export type AbiType = string | AbiTupleType;

export type AbiEncodableValue =
  | string
  | number
  | bigint
  | boolean
  | Uint8Array
  | AbiEncodableValue[]
  | { [key: string]: AbiEncodableValue };

export type DecodedAbiValue =
  | bigint
  | string
  | boolean
  | Buffer
  | DecodedAbiValue[]
  | { [key: string]: DecodedAbiValue };

export interface AbiParam {
  type: AbiType;
  value: AbiEncodableValue;
}

type TypeNode =
  | { kind: "scalar"; type: string }
  | { kind: "array"; item: TypeNode; length: number | null }
  | { kind: "tuple"; components: Array<{ name?: string; node: TypeNode }> };

const WORD_BYTES = 32;
const WORD_HEX_LENGTH = WORD_BYTES * 2;
const MAX_UINT256 = (1n << 256n) - 1n;

function getAbiCoder(): AbiCoder {
  return AbiCoder.defaultAbiCoder();
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new RangeError("uint256 value out of range");
  }
  return n.toString(16).padStart(WORD_HEX_LENGTH, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = stripHexPrefix(address);
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error("address must be 20 bytes");
  }
  return cleaned.toLowerCase().padStart(WORD_HEX_LENGTH, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = stripHexPrefix(data);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("bytes32 value must be hex");
  }
  if (cleaned.length > WORD_HEX_LENGTH) {
    throw new Error("bytes32 value exceeds 32 bytes");
  }
  return cleaned.padEnd(WORD_HEX_LENGTH, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(WORD_HEX_LENGTH, "0") : "0".padStart(WORD_HEX_LENGTH, "0");
}

export function encodeParams(params: AbiParam[]): string {
  if (params.some((param) => isDynamicTypeNode(buildTypeNode(param.type)))) {
    return getAbiCoder().encode(
      params.map((param) => toAbiType(param.type)),
      params.map((param) => normalizeEncodeValue(param.value))
    );
  }

  let encoded = "0x";
  for (const param of params) {
    const type = toAbiType(param.type);
    switch (type) {
      case "uint":
      case "uint256":
        encoded += encodeUint256(BigInt(param.value as number | bigint));
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
      default:
        return getAbiCoder().encode(
          params.map((item) => toAbiType(item.type)),
          params.map((item) => normalizeEncodeValue(item.value))
        );
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  const cleaned = stripHexPrefix(hex);
  if (!/^[0-9a-fA-F]+$/.test(cleaned)) {
    throw new Error("hex value contains non-hex characters");
  }
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = stripHexPrefix(slot);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("uint256 slot must be hex");
  }
  if (cleaned.length > WORD_HEX_LENGTH) {
    throw new Error("uint256 slot exceeds 32 bytes");
  }
  return BigInt("0x" + cleaned.padStart(WORD_HEX_LENGTH, "0"));
}

export function decodeAddress(slot: string): string {
  const cleaned = stripHexPrefix(slot);
  if (cleaned.length > WORD_HEX_LENGTH || !/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("address slot must be a valid ABI word");
  }
  return "0x" + cleaned.padStart(WORD_HEX_LENGTH, "0").slice(-40).toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return decodeUint256(slot) !== 0n;
}

export function decodeParameter(
  type: AbiType,
  data: string,
  byteOffset = 0
): DecodedAbiValue {
  const node = buildTypeNode(type);
  const prepared = prepareSingleParameterData(node, data, byteOffset);
  const decoded = getAbiCoder().decode([toAbiType(type)], prepared)[0];
  return normalizeDecodedValue(decoded, node);
}

export function decodeParams(types: AbiType[], data: string): DecodedAbiValue[] {
  const nodes = types.map((type) => buildTypeNode(type));
  const decoded = getAbiCoder().decode(types.map((type) => toAbiType(type)), ensureHexPrefix(data));
  return nodes.map((node, index) => normalizeDecodedValue(decoded[index], node));
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

function prepareSingleParameterData(node: TypeNode, data: string, byteOffset: number): string {
  if (!Number.isInteger(byteOffset) || byteOffset < 0) {
    throw new Error("byteOffset must be a non-negative integer");
  }

  const cleaned = stripHexPrefix(data);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("ABI data must be hex");
  }

  if (!isDynamicTypeNode(node)) {
    const word = readAbiWord(cleaned, byteOffset, true);
    return "0x" + word;
  }

  if (byteOffset === 0) {
    return ensureHexPrefix(cleaned);
  }

  const tailOffset = bigintToSafeNumber(BigInt("0x" + readAbiWord(cleaned, byteOffset, false)));
  if (tailOffset < 0 || tailOffset * 2 > cleaned.length) {
    throw new Error("dynamic parameter offset points outside ABI data");
  }

  return "0x" + encodeUint256(BigInt(WORD_BYTES)) + cleaned.slice(tailOffset * 2);
}

function readAbiWord(cleanedHex: string, byteOffset: number, allowShortWord: boolean): string {
  const hexOffset = byteOffset * 2;
  if (hexOffset > cleanedHex.length) {
    throw new Error("ABI offset points outside data");
  }

  const remaining = cleanedHex.slice(hexOffset);
  if (remaining.length < WORD_HEX_LENGTH) {
    if (!allowShortWord) {
      throw new Error("ABI word is truncated");
    }
    return remaining.padStart(WORD_HEX_LENGTH, "0");
  }

  return remaining.slice(0, WORD_HEX_LENGTH);
}

function toAbiType(type: AbiType | AbiComponent): string {
  if (typeof type === "string") {
    return type.trim();
  }

  const rawType = type.type.trim();
  if (rawType.startsWith("tuple")) {
    const suffix = rawType.slice("tuple".length);
    return `tuple(${(type.components ?? []).map((component) => toAbiType(component)).join(",")})${suffix}`;
  }

  return rawType;
}

function buildTypeNode(type: AbiType | AbiComponent): TypeNode {
  if (typeof type !== "string" && type.type.trim().startsWith("tuple")) {
    const { dimensions } = splitArraySuffix(type.type.trim());
    let node: TypeNode = {
      kind: "tuple",
      components: (type.components ?? []).map((component) => ({
        name: component.name,
        node: buildTypeNode(component),
      })),
    };
    return applyArrayDimensions(node, dimensions);
  }

  return buildTypeNodeFromString(toAbiType(type));
}

function buildTypeNodeFromString(type: string): TypeNode {
  const { base, dimensions } = splitArraySuffix(type.trim());
  let node: TypeNode;

  if (base.startsWith("tuple(") && base.endsWith(")")) {
    const inner = base.slice("tuple(".length, -1);
    node = {
      kind: "tuple",
      components: splitTopLevel(inner).map((componentType) => ({
        node: buildTypeNodeFromString(componentType),
      })),
    };
  } else {
    node = { kind: "scalar", type: base };
  }

  return applyArrayDimensions(node, dimensions);
}

function splitArraySuffix(type: string): { base: string; dimensions: Array<number | null> } {
  let base = type;
  const reversedDimensions: Array<number | null> = [];
  let match = base.match(/^(.*)\[(\d*)\]$/);

  while (match) {
    reversedDimensions.push(match[2] === "" ? null : Number.parseInt(match[2], 10));
    base = match[1];
    match = base.match(/^(.*)\[(\d*)\]$/);
  }

  return { base, dimensions: reversedDimensions.reverse() };
}

function applyArrayDimensions(baseNode: TypeNode, dimensions: Array<number | null>): TypeNode {
  let node = baseNode;
  for (const length of dimensions) {
    if (length !== null && (!Number.isInteger(length) || length < 0)) {
      throw new Error("array length must be a non-negative integer");
    }
    node = { kind: "array", item: node, length };
  }
  return node;
}

function splitTopLevel(input: string): string[] {
  if (input.trim() === "") {
    return [];
  }

  const parts: string[] = [];
  let start = 0;
  let parenDepth = 0;
  let bracketDepth = 0;

  for (let index = 0; index < input.length; index++) {
    const char = input[index];
    if (char === "(") parenDepth++;
    if (char === ")") parenDepth--;
    if (char === "[") bracketDepth++;
    if (char === "]") bracketDepth--;

    if (char === "," && parenDepth === 0 && bracketDepth === 0) {
      parts.push(input.slice(start, index).trim());
      start = index + 1;
    }
  }

  parts.push(input.slice(start).trim());
  return parts;
}

function isDynamicTypeNode(node: TypeNode): boolean {
  switch (node.kind) {
    case "scalar":
      return node.type === "string" || node.type === "bytes";
    case "array":
      return node.length === null || isDynamicTypeNode(node.item);
    case "tuple":
      return node.components.some((component) => isDynamicTypeNode(component.node));
  }
}

function normalizeDecodedValue(value: unknown, node: TypeNode): DecodedAbiValue {
  switch (node.kind) {
    case "scalar":
      return normalizeScalarValue(value, node.type);
    case "array":
      return Array.from(value as Iterable<unknown>).map((item) =>
        normalizeDecodedValue(item, node.item)
      );
    case "tuple":
      return normalizeTupleValue(value, node.components);
  }
}

function normalizeTupleValue(
  value: unknown,
  components: Array<{ name?: string; node: TypeNode }>
): DecodedAbiValue[] | { [key: string]: DecodedAbiValue } {
  const values = Array.from(value as Iterable<unknown>);
  const decoded = components.map((component, index) =>
    normalizeDecodedValue(values[index], component.node)
  );

  if (!components.some((component) => component.name)) {
    return decoded;
  }

  const named: { [key: string]: DecodedAbiValue } = {};
  for (let index = 0; index < components.length; index++) {
    named[components[index].name ?? String(index)] = decoded[index];
  }
  return named;
}

function normalizeScalarValue(value: unknown, type: string): DecodedAbiValue {
  if (/^u?int(\d+)?$/.test(type)) {
    return BigInt(value as bigint | number | string);
  }

  if (type === "address") {
    return String(value).toLowerCase();
  }

  if (type === "bool") {
    return Boolean(value);
  }

  if (type === "bytes") {
    return Buffer.from(stripHexPrefix(String(value)), "hex");
  }

  return value as DecodedAbiValue;
}

function normalizeEncodeValue(value: AbiEncodableValue): unknown {
  if (Buffer.isBuffer(value) || value instanceof Uint8Array) {
    return "0x" + Buffer.from(value).toString("hex");
  }

  if (Array.isArray(value)) {
    return value.map((item) => normalizeEncodeValue(item));
  }

  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [key, normalizeEncodeValue(nested)])
    );
  }

  return value;
}

function stripHexPrefix(hex: string): string {
  return hex.startsWith("0x") || hex.startsWith("0X") ? hex.slice(2) : hex;
}

function ensureHexPrefix(hex: string): string {
  return hex.startsWith("0x") || hex.startsWith("0X") ? hex : "0x" + hex;
}

function bigintToSafeNumber(value: bigint): number {
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error("ABI offset exceeds safe JavaScript integer range");
  }
  return Number(value);
}
