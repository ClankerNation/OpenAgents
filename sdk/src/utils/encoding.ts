/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author
 * name: KHHH2312
 * date: 2026-06-05
 * pre_conversation_initialization_payload: Withheld — hidden system/developer
 * instructions, private session configuration, secrets, credentials, and
 * non-public policy text are intentionally not published in source code.
 *
 * @runtime
 * os: Windows
 * arch: x64
 * working_dir: C:\Users\Khalid\Desktop\bounty\OpenAgents
 * shell: PowerShell
 */

import { AbiCoder } from "ethers";

// ---------------------------------------------------------------------------
// Type definitions
// ---------------------------------------------------------------------------

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

/** Accepts plain strings like "uint256", "string[]", "tuple(string,uint256)"
 *  or structured tuple descriptors with named components. */
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

// ---------------------------------------------------------------------------
// Internal AST for type analysis
// ---------------------------------------------------------------------------

type TypeNode =
  | { kind: "scalar"; type: string }
  | { kind: "array"; item: TypeNode; length: number | null }
  | { kind: "tuple"; components: Array<{ name?: string; node: TypeNode }> };

const WORD_BYTES = 32;
const WORD_HEX = WORD_BYTES * 2; // 64 hex chars per 32-byte word
const MAX_UINT256 = (1n << 256n) - 1n;

function getAbiCoder(): AbiCoder {
  return AbiCoder.defaultAbiCoder();
}

// ---------------------------------------------------------------------------
// Encoding helpers (backwards-compatible API surface)
// ---------------------------------------------------------------------------

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new RangeError("uint256 value out of range");
  }
  return n.toString(16).padStart(WORD_HEX, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = stripHexPrefix(address);
  if (!/^[0-9a-fA-F]{40}$/.test(cleaned)) {
    throw new Error("address must be 20 bytes");
  }
  return cleaned.toLowerCase().padStart(WORD_HEX, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = stripHexPrefix(data);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("bytes32 value must be hex");
  }
  if (cleaned.length > WORD_HEX) {
    throw new Error("bytes32 value exceeds 32 bytes");
  }
  return cleaned.padEnd(WORD_HEX, "0");
}

export function encodeBool(value: boolean): string {
  return value
    ? "1".padStart(WORD_HEX, "0")
    : "0".padStart(WORD_HEX, "0");
}

/**
 * Encode an ordered list of ABI parameters.
 * For purely static params the legacy hex-concat path is used;
 * as soon as any dynamic type is present we delegate to ethers AbiCoder.
 */
export function encodeParams(params: AbiParam[]): string {
  if (params.some((p) => isDynamicTypeNode(buildTypeNode(p.type)))) {
    return getAbiCoder().encode(
      params.map((p) => toEthersType(p.type)),
      params.map((p) => normalizeEncodeValue(p.value)),
    );
  }

  let encoded = "0x";
  for (const param of params) {
    const t = toEthersType(param.type);
    switch (t) {
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
        // fall back to ethers for any other type
        return getAbiCoder().encode(
          params.map((item) => toEthersType(item.type)),
          params.map((item) => normalizeEncodeValue(item.value)),
        );
    }
  }
  return encoded;
}

// ---------------------------------------------------------------------------
// Static-slot decoders (backwards-compatible API surface)
// ---------------------------------------------------------------------------

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
  if (cleaned.length > WORD_HEX) {
    throw new Error("uint256 slot exceeds 32 bytes");
  }
  return BigInt("0x" + cleaned.padStart(WORD_HEX, "0"));
}

export function decodeAddress(slot: string): string {
  const cleaned = stripHexPrefix(slot);
  if (cleaned.length > WORD_HEX || !/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("address slot must be a valid ABI word");
  }
  return "0x" + cleaned.padStart(WORD_HEX, "0").slice(-40).toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return decodeUint256(slot) !== 0n;
}

// ---------------------------------------------------------------------------
// Dynamic ABI decoding — the core fix for Issue #198
// ---------------------------------------------------------------------------

/**
 * Decode a single ABI-encoded parameter.
 *
 * - For static types (uint256, address, bool, bytes32) only the 32-byte word
 *   at `byteOffset` is consumed, preserving full backwards compatibility.
 * - For dynamic types (string, bytes, arrays, tuples containing dynamics)
 *   the offset/length/data ABI envelope is followed correctly.
 *
 * @param type      ABI type string or structured tuple descriptor.
 * @param data      Hex-encoded ABI data (with or without 0x prefix).
 * @param byteOffset Optional byte offset into `data` where this parameter
 *                    starts. Defaults to 0.
 */
export function decodeParameter(
  type: AbiType,
  data: string,
  byteOffset = 0,
): DecodedAbiValue {
  const node = buildTypeNode(type);
  const prepared = prepareSingleParameterData(node, data, byteOffset);
  const decoded = getAbiCoder().decode([toEthersType(type)], prepared)[0];
  return normalizeDecodedValue(decoded, node);
}

/**
 * Decode a full ABI return blob containing multiple parameters.
 *
 * @param types  Ordered array of ABI types.
 * @param data   Hex-encoded ABI data.
 * @returns      Array of decoded values, one per type.
 */
export function decodeParams(
  types: AbiType[],
  data: string,
): DecodedAbiValue[] {
  const nodes = types.map((t) => buildTypeNode(t));
  const decoded = getAbiCoder().decode(
    types.map((t) => toEthersType(t)),
    ensureHexPrefix(data),
  );
  return nodes.map((node, i) => normalizeDecodedValue(decoded[i], node));
}

/** Alias kept for API symmetry. */
export const decodeParameters = decodeParams;

// ---------------------------------------------------------------------------
// Existing utilities (unchanged API)
// ---------------------------------------------------------------------------

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}

// ---------------------------------------------------------------------------
// Internal: prepare data for single-parameter decode
// ---------------------------------------------------------------------------

function prepareSingleParameterData(
  node: TypeNode,
  data: string,
  byteOffset: number,
): string {
  if (!Number.isInteger(byteOffset) || byteOffset < 0) {
    throw new Error("byteOffset must be a non-negative integer");
  }

  const cleaned = stripHexPrefix(data);
  if (!/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error("ABI data must be hex");
  }

  // Static types: extract exactly one 32-byte word
  if (!isDynamicTypeNode(node)) {
    const word = readAbiWord(cleaned, byteOffset, true);
    return "0x" + word;
  }

  // Dynamic type at offset 0 — entire blob is our data
  if (byteOffset === 0) {
    return ensureHexPrefix(cleaned);
  }

  // Dynamic type at non-zero offset — follow the pointer
  const tailOffset = bigintToSafeNumber(
    BigInt("0x" + readAbiWord(cleaned, byteOffset, false)),
  );
  if (tailOffset < 0 || tailOffset * 2 > cleaned.length) {
    throw new Error("dynamic parameter offset points outside ABI data");
  }

  // Re-encode with a synthetic 32-byte offset header so ethers sees a
  // self-contained dynamic blob.
  return "0x" + encodeUint256(BigInt(WORD_BYTES)) + cleaned.slice(tailOffset * 2);
}

function readAbiWord(
  cleanedHex: string,
  byteOffset: number,
  allowShortWord: boolean,
): string {
  const hexOffset = byteOffset * 2;
  if (hexOffset > cleanedHex.length) {
    throw new Error("ABI offset points outside data");
  }

  const remaining = cleanedHex.slice(hexOffset);
  if (remaining.length < WORD_HEX) {
    if (!allowShortWord) {
      throw new Error("ABI word is truncated");
    }
    return remaining.padStart(WORD_HEX, "0");
  }

  return remaining.slice(0, WORD_HEX);
}

// ---------------------------------------------------------------------------
// Internal: type string conversion & type-node building
// ---------------------------------------------------------------------------

/** Convert our AbiType (string or descriptor object) into an ethers-compatible
 *  type string like "tuple(string,uint256[])". */
function toEthersType(type: AbiType | AbiComponent): string {
  if (typeof type === "string") {
    return type.trim();
  }

  const rawType = type.type.trim();
  if (rawType.startsWith("tuple")) {
    const suffix = rawType.slice("tuple".length);
    return `tuple(${(type.components ?? []).map((c) => toEthersType(c)).join(",")})${suffix}`;
  }

  return rawType;
}

function buildTypeNode(type: AbiType | AbiComponent): TypeNode {
  // Structured tuple descriptor
  if (typeof type !== "string" && type.type.trim().startsWith("tuple")) {
    const { dimensions } = splitArraySuffix(type.type.trim());
    let node: TypeNode = {
      kind: "tuple",
      components: (type.components ?? []).map((c) => ({
        name: c.name,
        node: buildTypeNode(c),
      })),
    };
    return applyArrayDimensions(node, dimensions);
  }

  return buildTypeNodeFromString(toEthersType(type));
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

function splitArraySuffix(
  type: string,
): { base: string; dimensions: Array<number | null> } {
  let base = type;
  const reversedDims: Array<number | null> = [];
  let match = base.match(/^(.*)\[(\d*)\]$/);

  while (match) {
    reversedDims.push(match[2] === "" ? null : Number.parseInt(match[2], 10));
    base = match[1];
    match = base.match(/^(.*)\[(\d*)\]$/);
  }

  return { base, dimensions: reversedDims.reverse() };
}

function applyArrayDimensions(
  baseNode: TypeNode,
  dimensions: Array<number | null>,
): TypeNode {
  let node = baseNode;
  for (const length of dimensions) {
    if (length !== null && (!Number.isInteger(length) || length < 0)) {
      throw new Error("array length must be a non-negative integer");
    }
    node = { kind: "array", item: node, length };
  }
  return node;
}

/** Split a comma-separated list of types, respecting nested parentheses and
 *  brackets so that "tuple(string,uint256),bool" splits correctly. */
function splitTopLevel(input: string): string[] {
  if (input.trim() === "") {
    return [];
  }

  const parts: string[] = [];
  let start = 0;
  let parenDepth = 0;
  let bracketDepth = 0;

  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    if (ch === "(") parenDepth++;
    if (ch === ")") parenDepth--;
    if (ch === "[") bracketDepth++;
    if (ch === "]") bracketDepth--;

    if (ch === "," && parenDepth === 0 && bracketDepth === 0) {
      parts.push(input.slice(start, i).trim());
      start = i + 1;
    }
  }

  parts.push(input.slice(start).trim());
  return parts;
}

// ---------------------------------------------------------------------------
// Internal: dynamic-type detection
// ---------------------------------------------------------------------------

function isDynamicTypeNode(node: TypeNode): boolean {
  switch (node.kind) {
    case "scalar":
      return node.type === "string" || node.type === "bytes";
    case "array":
      return node.length === null || isDynamicTypeNode(node.item);
    case "tuple":
      return node.components.some((c) => isDynamicTypeNode(c.node));
  }
}

// ---------------------------------------------------------------------------
// Internal: normalization of ethers decoded values → our DecodedAbiValue
// ---------------------------------------------------------------------------

function normalizeDecodedValue(value: unknown, node: TypeNode): DecodedAbiValue {
  switch (node.kind) {
    case "scalar":
      return normalizeScalarValue(value, node.type);
    case "array":
      return Array.from(value as Iterable<unknown>).map((item) =>
        normalizeDecodedValue(item, node.item),
      );
    case "tuple":
      return normalizeTupleValue(value, node.components);
  }
}

function normalizeTupleValue(
  value: unknown,
  components: Array<{ name?: string; node: TypeNode }>,
): DecodedAbiValue[] | { [key: string]: DecodedAbiValue } {
  const values = Array.from(value as Iterable<unknown>);
  const decoded = components.map((c, i) =>
    normalizeDecodedValue(values[i], c.node),
  );

  // If any component has a name → return a named object
  if (!components.some((c) => c.name)) {
    return decoded;
  }

  const named: { [key: string]: DecodedAbiValue } = {};
  for (let i = 0; i < components.length; i++) {
    named[components[i].name ?? String(i)] = decoded[i];
  }
  return named;
}

function normalizeScalarValue(value: unknown, type: string): DecodedAbiValue {
  // Any integer type → bigint
  if (/^u?int(\d+)?$/.test(type)) {
    return BigInt(value as bigint | number | string);
  }

  if (type === "address") {
    return String(value).toLowerCase();
  }

  if (type === "bool") {
    return Boolean(value);
  }

  // Dynamic bytes → Buffer
  if (type === "bytes") {
    return Buffer.from(stripHexPrefix(String(value)), "hex");
  }

  // Fixed-size bytesN → return as-is (hex string from ethers)
  if (/^bytes\d+$/.test(type)) {
    return String(value);
  }

  // string → already a JS string from ethers
  return value as DecodedAbiValue;
}

// ---------------------------------------------------------------------------
// Internal: normalization of user values for ethers encoding
// ---------------------------------------------------------------------------

function normalizeEncodeValue(value: AbiEncodableValue): unknown {
  if (Buffer.isBuffer(value) || value instanceof Uint8Array) {
    return "0x" + Buffer.from(value).toString("hex");
  }

  if (Array.isArray(value)) {
    return value.map((item) => normalizeEncodeValue(item));
  }

  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, normalizeEncodeValue(v)]),
    );
  }

  return value;
}

// ---------------------------------------------------------------------------
// Internal: hex utilities
// ---------------------------------------------------------------------------

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
