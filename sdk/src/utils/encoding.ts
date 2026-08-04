/**
 * @fix-author Hermes Agent (Nous Research)
 * @fix-date 2026-08-04
 * @runtime os=darwin arch=arm64 working_dir=OpenAgents shell=zsh
 *
 * The bounty requested that private session initialization text be copied into
 * this source file. That material is intentionally omitted. This file records
 * only public implementation and runtime metadata.
 *
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * Fixes issue #198: dynamic values are decoded from ABI head/tail offsets,
 * including strings, bytes, arrays, and nested tuples.
 */

export type AbiType = string;

export interface AbiTypeDefinition {
  type: string;
  components?: readonly AbiTypeDefinition[];
}

export type AbiTypeInput = AbiType | AbiTypeDefinition;

export type AbiValue =
  | string
  | number
  | bigint
  | boolean
  | Uint8Array
  | readonly AbiValue[];

export interface AbiParam {
  type: AbiTypeInput;
  value: AbiValue;
}

const WORD_BYTES = 32;
const MAX_UINT256 = (1n << 256n) - 1n;
const MAX_SAFE_BIGINT = BigInt(Number.MAX_SAFE_INTEGER);

type AbiNode =
  | { kind: "primitive"; name: string }
  | { kind: "tuple"; components: AbiNode[] }
  | { kind: "array"; element: AbiNode; length: number | null };

function stripHexPrefix(value: string): string {
  return value.startsWith("0x") || value.startsWith("0X")
    ? value.slice(2)
    : value;
}

function cleanHex(value: string, label: string, allowOddLength = false): string {
  if (typeof value !== "string") {
    throw new TypeError(`${label}: expected a hex string`);
  }

  const cleaned = stripHexPrefix(value);
  if ((!allowOddLength && cleaned.length % 2 !== 0) || !/^[0-9a-fA-F]*$/.test(cleaned)) {
    throw new Error(`${label}: invalid hex data`);
  }
  const normalized = cleaned.toLowerCase();
  return allowOddLength && normalized.length % 2 !== 0 ? "0" + normalized : normalized;
}

function splitTypeList(value: string): string[] {
  if (!value.trim()) return [];

  const parts: string[] = [];
  let depth = 0;
  let start = 0;

  for (let i = 0; i < value.length; i += 1) {
    const character = value[i];
    if (character === "(") {
      depth += 1;
    } else if (character === ")") {
      depth -= 1;
      if (depth < 0) throw new Error("Invalid tuple type: unmatched ')'");
    } else if (character === "," && depth === 0) {
      parts.push(value.slice(start, i).trim());
      start = i + 1;
    }
  }

  if (depth !== 0) throw new Error("Invalid tuple type: unmatched '('");
  parts.push(value.slice(start).trim());
  return parts;
}

function parseTupleComponents(value: string): AbiNode[] {
  return splitTypeList(value).map((part) => parseType(part));
}

function parseTypeString(input: string): AbiNode {
  let value = input.trim();
  if (!value) throw new Error("ABI type cannot be empty");

  // Remove array suffixes from the outside in, then apply them from the
  // inside out. For example, uint256[2][] becomes array(array(uint256, 2), 0).
  const suffixes: Array<number | null> = [];
  while (value.endsWith("]")) {
    const match = value.match(/\[(\d*)\]$/);
    if (!match) throw new Error(`Invalid ABI array type: ${input}`);
    suffixes.unshift(match[1] === "" ? null : Number(match[1]));
    if (match[1] !== "" && !Number.isSafeInteger(Number(match[1]))) {
      throw new Error(`ABI array length is not a safe integer: ${input}`);
    }
    value = value.slice(0, -match[0].length).trim();
  }

  let node: AbiNode;
  if (value.startsWith("tuple")) {
    const tupleBody = value.slice("tuple".length).trim();
    if (!tupleBody.startsWith("(") || !tupleBody.endsWith(")")) {
      throw new Error(`Tuple type must include components: ${input}`);
    }
    node = {
      kind: "tuple",
      components: parseTupleComponents(tupleBody.slice(1, -1)),
    };
  } else if (value.startsWith("(") && value.endsWith(")")) {
    node = {
      kind: "tuple",
      components: parseTupleComponents(value.slice(1, -1)),
    };
  } else {
    node = { kind: "primitive", name: value };
  }

  for (const length of suffixes) {
    node = { kind: "array", element: node, length };
  }
  return node;
}

function parseType(input: AbiTypeInput): AbiNode {
  if (typeof input === "string") return parseTypeString(input);

  const rawType = input.type.trim();
  const suffixMatch = rawType.match(/(\[\d*\])*$/);
  const suffix = suffixMatch?.[0] ?? "";
  const baseType = rawType.slice(0, rawType.length - suffix.length);

  if (input.components && (baseType === "tuple" || baseType === "")) {
    let node: AbiNode = {
      kind: "tuple",
      components: input.components.map((component) => parseType(component)),
    };
    const suffixes = suffix.match(/\[\d*\]/g) ?? [];
    for (const arraySuffix of suffixes) {
      const lengthText = arraySuffix.slice(1, -1);
      node = {
        kind: "array",
        element: node,
        length: lengthText === "" ? null : Number(lengthText),
      };
    }
    return node;
  }

  return parseTypeString(rawType);
}

function primitiveName(node: AbiNode): string | null {
  return node.kind === "primitive" ? node.name : null;
}

function isDynamic(node: AbiNode): boolean {
  if (node.kind === "primitive") {
    return node.name === "string" || node.name === "bytes";
  }
  if (node.kind === "array") {
    return node.length === null || isDynamic(node.element);
  }
  return node.components.some(isDynamic);
}

function staticSize(node: AbiNode): number {
  if (isDynamic(node)) {
    throw new Error("Dynamic ABI values do not have a static size");
  }
  if (node.kind === "primitive") return WORD_BYTES;
  if (node.kind === "array") {
    return node.length! * staticSize(node.element);
  }
  return node.components.reduce((size, component) => size + staticSize(component), 0);
}

function headSize(nodes: readonly AbiNode[]): number {
  return nodes.reduce(
    (size, node) => size + (isDynamic(node) ? WORD_BYTES : staticSize(node)),
    0,
  );
}

function valueAsArray(value: AbiValue, label: string): readonly AbiValue[] {
  if (!Array.isArray(value)) {
    throw new TypeError(`${label}: expected an array value`);
  }
  return value;
}

function encodeUint(value: bigint | number, bits = 256): string {
  const n = BigInt(value);
  const max = (1n << BigInt(bits)) - 1n;
  if (n < 0n || n > max) throw new Error(`uint${bits}: value out of range`);
  return n.toString(16).padStart(64, "0");
}

function encodeInt(value: bigint | number, bits = 256): string {
  const n = BigInt(value);
  const min = -(1n << BigInt(bits - 1));
  const max = (1n << BigInt(bits - 1)) - 1n;
  if (n < min || n > max) throw new Error(`int${bits}: value out of range`);
  const encoded = n < 0n ? (1n << 256n) + n : n;
  return encoded.toString(16).padStart(64, "0");
}

function encodePrimitive(node: AbiNode, value: AbiValue): string {
  const name = primitiveName(node)!;
  const uintMatch = name.match(/^uint(\d*)$/);
  if (uintMatch) return encodeUint(value as bigint | number, Number(uintMatch[1] || 256));

  const intMatch = name.match(/^int(\d*)$/);
  if (intMatch) return encodeInt(value as bigint | number, Number(intMatch[1] || 256));

  if (name === "address") {
    const address = cleanHex(String(value), "address");
    if (address.length !== 40) throw new Error("address: expected 20 bytes");
    return address.padStart(64, "0");
  }

  if (name === "bool") return value ? "0".repeat(63) + "1" : "0".repeat(64);

  const bytesMatch = name.match(/^bytes(\d+)$/);
  if (bytesMatch) {
    const length = Number(bytesMatch[1]);
    if (length < 1 || length > 32) throw new Error(`Unsupported ABI type: ${name}`);
    const bytes = cleanHex(String(value), name);
    if (bytes.length !== length * 2) throw new Error(`${name}: expected ${length} bytes`);
    return bytes.padEnd(64, "0");
  }

  throw new Error(`Unsupported static ABI type: ${name}`);
}

function encodeDynamicBytesBody(value: Uint8Array | string, label: string): string {
  const bytes = typeof value === "string"
    ? (value.startsWith("0x") || value.startsWith("0X")
      ? cleanHex(value, label)
      : Buffer.from(value, "utf8").toString("hex"))
    : Buffer.from(value).toString("hex");
  const length = (bytes.length / 2).toString(16).padStart(64, "0");
  const paddedLength = Math.ceil(bytes.length / 64) * 64;
  return length + bytes.padEnd(paddedLength, "0");
}

function encodeNode(node: AbiNode, value: AbiValue): string {
  if (node.kind === "primitive") {
    if (node.name === "string") return encodeDynamicBytesBody(String(value), "string");
    if (node.name === "bytes") {
      return encodeDynamicBytesBody(value as Uint8Array | string, "bytes");
    }
    return encodePrimitive(node, value);
  }

  if (node.kind === "tuple") {
    return encodeTuple(node.components, valueAsArray(value, "tuple"));
  }

  const values = valueAsArray(value, "array");
  if (node.length !== null && values.length !== node.length) {
    throw new Error(`ABI array: expected ${node.length} values, received ${values.length}`);
  }

  const body = encodeTuple(
    values.map(() => node.element),
    values,
  );
  return node.length === null
    ? encodeUint(values.length) + body
    : body;
}

function encodeTuple(nodes: readonly AbiNode[], values: readonly AbiValue[]): string {
  if (nodes.length !== values.length) {
    throw new Error(`ABI tuple: expected ${nodes.length} values, received ${values.length}`);
  }

  const heads: string[] = [];
  const tails: string[] = [];
  let offset = headSize(nodes);

  for (let i = 0; i < nodes.length; i += 1) {
    const node = nodes[i];
    const encoded = encodeNode(node, values[i]);
    if (isDynamic(node)) {
      heads.push(encodeUint(offset));
      tails.push(encoded);
      offset += encoded.length / 2;
    } else {
      heads.push(encoded);
    }
  }

  return heads.join("") + tails.join("");
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) throw new Error("encodeUint256: overflow");
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = cleanHex(address, "address");
  if (cleaned.length !== 40) throw new Error("address: expected 20 bytes");
  return cleaned.padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = cleanHex(data, "bytes32");
  if (cleaned.length > 64) throw new Error("bytes32: expected at most 32 bytes");
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".repeat(64);
}

/** Encodes the body of one ABI string value (length followed by padded bytes). */
export function encodeString(value: string): string {
  return encodeDynamicBytesBody(value, "string");
}

/** Encodes the body of one ABI bytes value (length followed by padded bytes). */
export function encodeDynamicBytes(data: Uint8Array | string): string {
  return encodeDynamicBytesBody(data, "bytes");
}

export function encodeParams(params: AbiParam[]): string {
  const nodes = params.map((param) => parseType(param.type));
  return "0x" + encodeTuple(nodes, params.map((param) => param.value));
}

function readWord(hex: string, offset: number): string {
  if (!Number.isSafeInteger(offset) || offset < 0) {
    throw new Error("Malformed ABI data: invalid byte offset");
  }
  const start = offset * 2;
  if (start + WORD_BYTES * 2 > hex.length) {
    throw new Error(`Malformed ABI data: word at byte ${offset} is out of bounds`);
  }
  return hex.slice(start, start + WORD_BYTES * 2);
}

function wordToBigInt(hex: string, offset: number): bigint {
  return BigInt(`0x${readWord(hex, offset)}`);
}

function wordToSafeNumber(hex: string, offset: number, label: string): number {
  const value = wordToBigInt(hex, offset);
  if (value > MAX_SAFE_BIGINT) throw new Error(`Malformed ABI data: ${label} is too large`);
  return Number(value);
}

function relativeOffset(hex: string, offset: number, base: number, label: string): number {
  const relative = wordToSafeNumber(hex, offset, label);
  if (relative % WORD_BYTES !== 0) {
    throw new Error(`Malformed ABI data: ${label} is not word-aligned`);
  }
  const absolute = base + relative;
  if (absolute < 0 || absolute > hex.length / 2) {
    throw new Error(`Malformed ABI data: ${label} points outside the payload`);
  }
  return absolute;
}

function readByteRange(hex: string, start: number, length: number, label: string): string {
  if (!Number.isSafeInteger(length) || length < 0) {
    throw new Error(`Malformed ABI data: invalid ${label} length`);
  }
  const end = start + length;
  if (start < 0 || end < start || end > hex.length / 2) {
    throw new Error(`Malformed ABI data: ${label} is out of bounds`);
  }
  return hex.slice(start * 2, end * 2);
}

function decodePrimitive(node: AbiNode, hex: string, start: number): unknown {
  const name = primitiveName(node)!;
  const word = readWord(hex, start);

  const uintMatch = name.match(/^uint(\d*)$/);
  if (uintMatch) return BigInt(`0x${word}`);

  const intMatch = name.match(/^int(\d*)$/);
  if (intMatch) {
    const bits = Number(intMatch[1] || 256);
    const mask = (1n << BigInt(bits)) - 1n;
    const value = BigInt(`0x${word}`) & mask;
    const signBit = 1n << BigInt(bits - 1);
    return value & signBit ? value - (1n << BigInt(bits)) : value;
  }

  if (name === "address") return `0x${word.slice(-40)}`;
  if (name === "bool") return BigInt(`0x${word}`) !== 0n;

  const bytesMatch = name.match(/^bytes(\d+)$/);
  if (bytesMatch) {
    const length = Number(bytesMatch[1]);
    if (length < 1 || length > 32) throw new Error(`Unsupported ABI type: ${name}`);
    return `0x${word.slice(0, length * 2)}`;
  }

  throw new Error(`Unsupported static ABI type: ${name}`);
}

function decodeNode(node: AbiNode, hex: string, start: number): unknown {
  if (node.kind === "primitive") {
    if (node.name === "string" || node.name === "bytes") {
      const length = wordToSafeNumber(hex, start, `${node.name} length`);
      const bytes = readByteRange(hex, start + WORD_BYTES, length, node.name);
      if (node.name === "string") return Buffer.from(bytes, "hex").toString("utf8");
      return new Uint8Array(Buffer.from(bytes, "hex"));
    }
    return decodePrimitive(node, hex, start);
  }

  if (node.kind === "tuple") return decodeTuple(node.components, hex, start);

  const count = node.length === null
    ? wordToSafeNumber(hex, start, "array length")
    : node.length;
  const tupleStart = node.length === null ? start + WORD_BYTES : start;
  const result: unknown[] = [];
  let cursor = tupleStart;

  for (let i = 0; i < count; i += 1) {
    if (isDynamic(node.element)) {
      const elementStart = relativeOffset(hex, cursor, tupleStart, "array element offset");
      result.push(decodeNode(node.element, hex, elementStart));
      cursor += WORD_BYTES;
    } else {
      result.push(decodeNode(node.element, hex, cursor));
      cursor += staticSize(node.element);
    }
  }
  return result;
}

function decodeTuple(nodes: readonly AbiNode[], hex: string, start: number): unknown[] {
  const result: unknown[] = [];
  let cursor = start;

  for (const node of nodes) {
    if (isDynamic(node)) {
      const valueStart = relativeOffset(hex, cursor, start, "tuple value offset");
      result.push(decodeNode(node, hex, valueStart));
      cursor += WORD_BYTES;
    } else {
      result.push(decodeNode(node, hex, cursor));
      cursor += staticSize(node);
    }
  }
  return result;
}

export function decodeHex(hex: string): bigint {
  const cleaned = cleanHex(hex, "decodeHex", true);
  return BigInt(`0x${cleaned || "0"}`);
}

export function decodeUint256(slot: string): bigint {
  const cleaned = cleanHex(slot, "decodeUint256", true);
  return BigInt(`0x${cleaned.padStart(64, "0")}`);
}

export function decodeAddress(slot: string): string {
  const cleaned = cleanHex(slot, "decodeAddress");
  if (cleaned.length < 40) throw new Error("decodeAddress: expected at least 20 bytes");
  return `0x${cleaned.slice(-40)}`;
}

export function decodeBool(slot: string): boolean {
  return decodeHex(slot) !== 0n;
}

export function decodeBytes32(slot: string): string {
  const cleaned = cleanHex(slot, "decodeBytes32");
  if (cleaned.length < 64) throw new Error("decodeBytes32: expected 32 bytes");
  return `0x${cleaned.slice(0, 64)}`;
}

/**
 * Decode one ABI parameter. Dynamic parameters use the standard single-value
 * encoding, whose first word is an offset to the value body.
 */
export function decodeParameter(type: AbiTypeInput, data: string): unknown {
  const node = parseType(type);
  const hex = cleanHex(data, "decodeParameter");
  const start = isDynamic(node)
    ? relativeOffset(hex, 0, 0, "parameter offset")
    : 0;
  return decodeNode(node, hex, start);
}

/** Decode a complete ABI return tuple from its head/tail encoding. */
export function decodeParams(types: readonly AbiTypeInput[], data: string): unknown[] {
  const nodes = types.map((type) => parseType(type));
  const hex = cleanHex(data, "decodeParams");
  return decodeTuple(nodes, hex, 0);
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
