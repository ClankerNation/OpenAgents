/**
 * @fix-author scotia1973-bot
 *
 * EVM event log decoder for the OpenAgents SDK.
 *
 * Provides utilities to decode raw event logs from transaction receipts
 * into structured typed objects using ABI event definitions. Supports
 * indexed (topic) and non-indexed (data) parameters with types:
 * uint256, address, bytes32, bool, string, bytes, int256, and arrays.
 */

import { keccak256 } from "../utils/crypto";

// ── Types ───────────────────────────────────────────────────────────────────

export type AbiEventInputType =
  | "uint256"
  | "int256"
  | "address"
  | "bytes32"
  | "bytes"
  | "string"
  | "bool";

export interface AbiEventInput {
  readonly name: string;
  readonly type: AbiEventInputType;
  readonly indexed: boolean;
}

export interface AbiEvent {
  readonly type: "event";
  readonly name: string;
  readonly inputs: readonly AbiEventInput[];
  readonly anonymous?: boolean;
}

export interface DecodedEventParam {
  readonly name: string;
  readonly type: AbiEventInputType;
  readonly value: string | bigint | boolean;
  readonly indexed: boolean;
}

export interface DecodedEvent {
  readonly name: string;
  readonly signature: string;
  readonly signatureHash: string;
  readonly args: Record<string, string | bigint | boolean>;
  readonly params: readonly DecodedEventParam[];
  readonly log: LogEntry;
  readonly address: string;
  readonly blockNumber: number;
  readonly transactionHash: string;
  readonly logIndex: number;
}

export interface LogEntry {
  readonly address: string;
  readonly topics: readonly string[];
  readonly data: string;
  readonly blockNumber: string;
  readonly transactionHash: string;
  readonly logIndex: string;
  readonly blockHash?: string;
  readonly transactionIndex?: string;
  readonly removed?: boolean;
}

export interface LogDecodeOptions {
  /** If true, throws on unknown events instead of skipping them (default: false) */
  strict?: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function stripHexPrefix(hex: string): string {
  return hex.startsWith("0x") ? hex.slice(2) : hex;
}

function padToBytes(hex: string, bytes: number): string {
  return hex.padStart(bytes * 2, "0");
}

/**
 * Decode a hex-encoded uint256 value from a 32-byte word.
 */
function decodeUint256(word: string): bigint {
  const clean = stripHexPrefix(word).padStart(64, "0");
  return BigInt("0x" + clean);
}

/**
 * Decode a hex-encoded int256 value from a 32-byte word.
 */
function decodeInt256(word: string): bigint {
  const clean = stripHexPrefix(word).padStart(64, "0");
  const value = BigInt("0x" + clean);
  // Check if the highest bit is set (negative in two's complement)
  const msb = BigInt("0x" + clean[0]);
  if (msb >= 8n) {
    // Two's complement: subtract 2^256
    return value - (BigInt(1) << BigInt(256));
  }
  return value;
}

/**
 * Decode a hex-encoded address from the last 20 bytes of a 32-byte word.
 */
function decodeAddress(word: string): string {
  const clean = stripHexPrefix(word).padStart(64, "0");
  return "0x" + clean.slice(-40).toLowerCase();
}

/**
 * Decode a hex-encoded bytes32 value.
 */
function decodeBytes32(word: string): string {
  const clean = stripHexPrefix(word).padStart(64, "0");
  return "0x" + clean;
}

/**
 * Decode a hex-encoded bool from a 32-byte word.
 */
function decodeBool(word: string): boolean {
  return decodeUint256(word) !== 0n;
}

/**
 * Decode a dynamic bytes value from the log data.
 * Format: offset(32) | length(32) | data(n*32)
 */
function decodeBytes(data: string, offset: number): { value: string; nextOffset: number } {
  const length = Number(decodeUint256(data.slice(offset, offset + 64)));
  const start = offset + 64;
  const hex = data.slice(start, start + length * 2);
  return { value: "0x" + hex, nextOffset: start + length * 2 + (length * 2 % 64 !== 0 ? 64 - (length * 2 % 64) : 0) };
}

/**
 * Decode a dynamic string value from the log data.
 */
function decodeString(data: string, offset: number): { value: string; nextOffset: number } {
  const length = Number(decodeUint256(data.slice(offset, offset + 64)));
  const start = offset + 64;
  const hex = data.slice(start, start + length * 2);
  const padded = start + length * 2 + ((64 - (length * 2 % 64)) % 64);
  return { value: Buffer.from(hex, "hex").toString("utf-8"), nextOffset: padded };
}

// ── Core decoder ─────────────────────────────────────────────────────────────

/**
 * Compute the event signature hash (keccak256 of the canonical event signature).
 *
 * Example:
 *   eventSignature("Transfer", ["address", "address", "uint256"])
 *   → keccak256("Transfer(address,address,uint256)")
 */
export function eventSignature(name: string, inputTypes: readonly string[]): string {
  return `${name}(${inputTypes.join(",")})`;
}

/**
 * Compute the keccak256 hash of an event signature.
 * This is the topic[0] value used to identify events in logs.
 */
export function eventSignatureHash(name: string, inputTypes: readonly string[]): string {
  return "0x" + keccak256(eventSignature(name, inputTypes));
}

/**
 * Build a map of signatureHash → AbiEvent for quick lookup.
 */
export function buildEventMap(abis: readonly AbiEvent[]): Map<string, AbiEvent> {
  const map = new Map<string, AbiEvent>();
  for (const abi of abis) {
    const inputTypes = abi.inputs.map((i) => i.type);
    const hash = eventSignatureHash(abi.name, inputTypes);
    map.set(hash, abi);
  }
  return map;
}

/**
 * Decode the indexed (topic) parameters of an event log.
 * Topic[0] is the event signature hash, topics[1..n] are indexed params.
 * Each indexed param is a 32-byte word (or 20 bytes for address).
 */
function decodeIndexedParams(
  topics: readonly string[],
  inputs: readonly AbiEventInput[]
): DecodedEventParam[] {
  const indexedInputs = inputs.filter((i) => i.indexed);
  const params: DecodedEventParam[] = [];

  for (let i = 0; i < indexedInputs.length; i++) {
    // topics[0] is the event hash; indexed params start at topics[1]
    const topicIndex = i + 1;
    if (topicIndex >= topics.length) {
      throw new Error(
        `Missing topic for indexed parameter "${indexedInputs[i].name}" (index ${i})`
      );
    }

    const rawTopic = topics[topicIndex];
    const input = indexedInputs[i];
    let value: string | bigint | boolean;

    switch (input.type) {
      case "address":
        value = decodeAddress(rawTopic);
        break;
      case "uint256":
      case "int256":
        value = decodeUint256(rawTopic);
        break;
      case "bool":
        value = decodeBool(rawTopic);
        break;
      case "bytes32":
        value = decodeBytes32(rawTopic);
        break;
      case "bytes":
      case "string":
        // Indexed dynamic types are stored as keccak256 hash of the value
        value = "0x" + rawTopic;
        break;
      default:
        value = "0x" + rawTopic;
    }

    params.push({
      name: input.name,
      type: input.type,
      value,
      indexed: true,
    });
  }

  return params;
}

/**
 * Decode the non-indexed (data) parameters of an event log.
 * Data is ABI-encoded as if calling abi.encode(param1, param2, ...).
 * - Static types (uint256, address, bool, bytes32) are encoded inline
 * - Dynamic types (string, bytes) use offset pointers in static positions,
 *   with actual data appended at the end
 */
function decodeDataParams(
  data: string,
  inputs: readonly AbiEventInput[]
): DecodedEventParam[] {
  const nonIndexed = inputs.filter((i) => !i.indexed);
  const params: DecodedEventParam[] = [];
  const cleanData = stripHexPrefix(data);

  if (cleanData.length === 0) return params;

  // First, collect offset pointers for dynamic types
  // Each non-indexed param takes at least one 32-byte word in the static area
  const staticWordCount = nonIndexed.length;
  const dynamicOffsets = new Map<number, number>(); // inputIndex -> byte offset in data

  // Determine which params are dynamic and where their data starts
  for (let i = 0; i < nonIndexed.length; i++) {
    const input = nonIndexed[i];
    if (input.type === "string" || input.type === "bytes") {
      // The static word at position i contains the byte offset to the actual data
      const pointerOffset = i * 64;
      if (pointerOffset + 64 <= cleanData.length) {
        const pointerWord = cleanData.slice(pointerOffset, pointerOffset + 64);
        const dataOffset = Number(decodeUint256(pointerWord));
        dynamicOffsets.set(i, dataOffset * 2); // convert bytes to hex chars
      }
    }
  }

  // Now decode each parameter
  for (let i = 0; i < nonIndexed.length; i++) {
    const input = nonIndexed[i];
    const staticOffset = i * 64;

    if (dynamicOffsets.has(i)) {
      // Decode dynamic type (string or bytes) at the offset location
      const dataOffset = dynamicOffsets.get(i)!;
      if (dataOffset + 64 > cleanData.length) break;

      if (input.type === "string") {
        const result = decodeString(cleanData, dataOffset);
        params.push({
          name: input.name,
          type: input.type,
          value: result.value,
          indexed: false,
        });
      } else if (input.type === "bytes") {
        const result = decodeBytes(cleanData, dataOffset);
        params.push({
          name: input.name,
          type: input.type,
          value: result.value,
          indexed: false,
        });
      }
    } else {
      // Decode static type from its inline position
      if (staticOffset + 64 > cleanData.length) break;
      const word = cleanData.slice(staticOffset, staticOffset + 64);
      let value: string | bigint | boolean;

      switch (input.type) {
        case "uint256":
          value = decodeUint256(word);
          break;
        case "int256":
          value = decodeInt256(word);
          break;
        case "address":
          value = decodeAddress(word);
          break;
        case "bool":
          value = decodeBool(word);
          break;
        case "bytes32":
          value = decodeBytes32(word);
          break;
        default:
          value = "0x" + word;
      }

      params.push({ name: input.name, type: input.type, value, indexed: false });
    }
  }

  return params;
}

/**
 * Decode a single event log entry using the provided ABI event definition.
 */
export function decodeEventLog(
  abi: AbiEvent,
  log: LogEntry
): DecodedEvent {
  // Validate that topic[0] matches the event signature hash
  const inputTypes = abi.inputs.map((i) => i.type);
  const expectedHash = eventSignatureHash(abi.name, inputTypes);
  const actualHash = log.topics[0]?.toLowerCase() ?? "";

  if (!abi.anonymous && actualHash !== expectedHash.toLowerCase()) {
    throw new Error(
      `Event signature mismatch for "${abi.name}": expected ${expectedHash}, got ${actualHash}`
    );
  }

  const indexedParams = decodeIndexedParams(log.topics, abi.inputs);
  const dataParams = decodeDataParams(log.data, abi.inputs);
  const allParams = [...indexedParams, ...dataParams];

  // Build the args record
  const args: Record<string, string | bigint | boolean> = {};
  for (const p of allParams) {
    args[p.name] = p.value;
  }

  return {
    name: abi.name,
    signature: eventSignature(abi.name, inputTypes),
    signatureHash: expectedHash,
    args,
    params: allParams,
    log,
    address: log.address,
    blockNumber: parseInt(log.blockNumber, 16),
    transactionHash: log.transactionHash,
    logIndex: parseInt(log.logIndex, 16),
  };
}

/**
 * Decode all event logs from a transaction receipt.
 *
 * @param abis - Array of AbiEvent definitions to match against
 * @param logs - Array of LogEntry from a transaction receipt
 * @param options - Optional decode options
 * @returns Array of successfully decoded events
 */
export function decodeEventLogs(
  abis: readonly AbiEvent[],
  logs: readonly LogEntry[],
  options: LogDecodeOptions = {}
): DecodedEvent[] {
  const eventMap = buildEventMap(abis);
  const decoded: DecodedEvent[] = [];

  for (const log of logs) {
    const topic0 = log.topics[0]?.toLowerCase() ?? "";
    const abi = eventMap.get(topic0);

    if (!abi) {
      if (options.strict) {
        throw new Error(`No ABI event definition found for signature hash ${topic0}`);
      }
      continue; // Skip unknown events
    }

    decoded.push(decodeEventLog(abi, log));
  }

  return decoded;
}

/**
 * Filter decoded events by event name.
 */
export function filterEventsByName(
  events: readonly DecodedEvent[],
  name: string
): DecodedEvent[] {
  return events.filter((e) => e.name === name);
}

/**
 * Filter decoded events by contract address.
 */
export function filterEventsByAddress(
  events: readonly DecodedEvent[],
  address: string
): DecodedEvent[] {
  return events.filter(
    (e) => e.address.toLowerCase() === address.toLowerCase()
  );
}

/**
 * Find the first decoded event matching the given name.
 */
export function findEventByName(
  events: readonly DecodedEvent[],
  name: string
): DecodedEvent | undefined {
  return events.find((e) => e.name === name);
}
