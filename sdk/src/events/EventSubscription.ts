/**
 * @fix-author kejuunuy
 * @fix-date 2026-05-30
 * @fix-issue 196
 * @fix-description Add event subscription and decoding to OpenAgents SDK
 */

import { EventEmitter } from "events";
import { createHash } from "crypto";
import {
  WebSocketProvider,
  WsProviderConfig,
} from "../providers/websocket";

/** Minimal ABI event input descriptor */
export interface AbiEventInput {
  name: string;
  type: string;
  indexed?: boolean;
}

/** ABI event entry (subset of full ABI JSON) */
export interface AbiEventEntry {
  type: "event";
  name: string;
  inputs: AbiEventInput[];
  anonymous?: boolean;
}

/** Decoded event log returned to the subscriber callback */
export interface DecodedEventLog {
  event: string;
  address: string;
  blockNumber: number | null;
  transactionHash: string | null;
  logIndex: number | null;
  args: Record<string, unknown>;
  raw: RawLog;
}

/** Raw log as received from the node */
export interface RawLog {
  address: string;
  topics: string[];
  data: string;
  blockNumber: string | null;
  transactionHash: string | null;
  logIndex: string | null;
  blockHash?: string;
  transactionIndex?: string;
  removed?: boolean;
}

/** Filter criteria for indexed event parameters */
export interface EventFilter {
  [paramName: string]: string | number | bigint | boolean;
}

/** Subscription handle returned to the caller */
export interface SubscriptionHandle {
  subscriptionId: string;
  unsubscribe: () => Promise<void>;
}

/** Configuration for an event subscription */
export interface EventSubscriptionConfig {
  /** WebSocket provider config or an existing provider instance */
  wsConfig?: WsProviderConfig;
  wsProvider?: WebSocketProvider;
  /** Default reconnect settings */
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}

// ──────────────────────────────────────────────────────
//  ABI helpers (keccak256 of canonical event signatures)
// ──────────────────────────────────────────────────────

function keccak256Hex(input: string): string {
  return createHash("sha3-256").update(Buffer.from(input, "utf-8")).digest("hex");
}

/**
 * Compute the topic-0 (event signature hash) for an event ABI entry.
 * e.g. Transfer(address,address,uint256) → keccak256(...)
 */
export function computeEventTopic(abiEvent: AbiEventEntry): string {
  const signature = buildCanonicalSignature(abiEvent);
  return "0x" + keccak256Hex(signature);
}

function buildCanonicalSignature(abiEvent: AbiEventEntry): string {
  const paramTypes = abiEvent.inputs.map((inp) => canonicalType(inp.type));
  return `${abiEvent.name}(${paramTypes.join(",")})`;
}

/**
 * Normalize tuple / array types to their canonical form for hashing.
 */
function canonicalType(t: string): string {
  // Normalise "uint" → "uint256", "int" → "int256", "byte" → "bytes1"
  if (t === "uint") return "uint256";
  if (t === "int") return "int256";
  if (t === "byte") return "bytes1";
  return t;
}

// ──────────────────────────────────────────────────────
//  ABI-based log decoding (without ethers dependency)
// ──────────────────────────────────────────────────────

/**
 * Decode a raw log against a known ABI event definition.
 * Indexed parameters come from `topics`, non-indexed from `data`.
 */
export function decodeEventLog(
  abiEvent: AbiEventEntry,
  log: RawLog
): Record<string, unknown> {
  const indexedInputs = abiEvent.inputs.filter((i) => i.indexed);
  const nonIndexedInputs = abiEvent.inputs.filter((i) => !i.indexed);

  const args: Record<string, unknown> = {};

  // Decode indexed params from topics (topic[0] is the event sig)
  for (let i = 0; i < indexedInputs.length; i++) {
    const input = indexedInputs[i];
    const topicHex = log.topics[i + 1]; // +1 because topics[0] is event signature
    if (!topicHex) continue;

    if (input.type === "string" || input.type === "bytes" || input.type.includes("[")) {
      // For dynamic types, topics contain the keccak256 hash — store the hash
      args[input.name] = topicHex;
    } else {
      args[input.name] = decodeSingleValue(input.type, topicHex);
    }
  }

  // Decode non-indexed params from data
  if (nonIndexedInputs.length > 0 && log.data && log.data !== "0x") {
    const decoded = decodeAbiData(nonIndexedInputs.map((i) => i.type), log.data);
    for (let i = 0; i < nonIndexedInputs.length; i++) {
      args[nonIndexedInputs[i].name] = decoded[i];
    }
  }

  return args;
}

/**
 * Decode a single ABI-encoded value from a 32-byte hex word.
 */
export function decodeSingleValue(type: string, hexWord: string): unknown {
  const raw = hexWord.startsWith("0x") ? hexWord.slice(2) : hexWord;
  const normalized = raw.padStart(64, "0");

  if (type === "address") {
    return "0x" + normalized.slice(24);
  }
  if (type === "bool") {
    return BigInt("0x" + normalized) !== 0n;
  }
  if (type.startsWith("uint")) {
    return BigInt("0x" + normalized);
  }
  if (type.startsWith("int")) {
    const val = BigInt("0x" + normalized);
    const bits = parseInt(type.slice(3) || "256");
    const max = 1n << BigInt(bits - 1);
    return val >= max ? val - (1n << BigInt(bits)) : val;
  }
  if (type === "bytes32") {
    return "0x" + normalized;
  }
  if (type.startsWith("bytes")) {
    return "0x" + normalized;
  }
  // Fallback: return raw hex
  return "0x" + normalized;
}

/**
 * Decode ABI-encoded data for a list of types.
 * Supports: uint/int (8–256), address, bool, bytes32, string (static slots only).
 */
export function decodeAbiData(types: string[], hexData: string): unknown[] {
  const data = hexData.startsWith("0x") ? hexData.slice(2) : hexData;
  const results: unknown[] = [];

  for (let i = 0; i < types.length; i++) {
    const offset = i * 64;
    const word = data.slice(offset, offset + 64);
    if (word.length < 64) {
      // Short data — left-pad
      results.push(decodeSingleValue(types[i], word.padStart(64, "0")));
    } else {
      results.push(decodeSingleValue(types[i], word));
    }
  }

  return results;
}

// ──────────────────────────────────────────────────────
//  EventSubscriptionManager
// ──────────────────────────────────────────────────────

interface ActiveSubscription {
  id: string;
  abiEvent: AbiEventEntry;
  contractAddress: string;
  callback: (log: DecodedEventLog) => void;
  filter?: EventFilter;
  topic0: string;
}

export class EventSubscriptionManager extends EventEmitter {
  private wsProvider: WebSocketProvider | null = null;
  private wsConfig: WsProviderConfig | null = null;
  private activeSubscriptions = new Map<string, ActiveSubscription>();
  private resubscribeCallbacks: Array<() => Promise<void>> = [];
  private _connected = false;

  constructor(config: EventSubscriptionConfig = {}) {
    super();
    if (config.wsProvider) {
      this.wsProvider = config.wsProvider;
    }
    if (config.wsConfig) {
      this.wsConfig = config.wsConfig;
    }
  }

  /**
   * Connect the underlying WebSocket provider.
   * If an existing provider was passed, uses that.
   */
  async connect(): Promise<void> {
    if (this._connected && this.wsProvider) return;

    if (!this.wsProvider) {
      if (!this.wsConfig) {
        throw new Error("No WebSocket config or provider supplied");
      }
      this.wsProvider = new WebSocketProvider(this.wsConfig);
    }

    // Listen for reconnects to resubscribe
    this.wsProvider.on("connected", () => {
      this._connected = true;
      this.resubscribeAll();
    });
    this.wsProvider.on("disconnected", () => {
      this._connected = false;
      this.emit("disconnected");
    });
    this.wsProvider.on("maxReconnectsReached", () => {
      this.emit("maxReconnectsReached");
    });

    await this.wsProvider.connect();
    this._connected = true;
  }

  /**
   * Subscribe to a contract event.
   *
   * @param contractAddress - The contract to listen to
   * @param abiEvent        - The ABI event definition
   * @param callback        - Called with decoded log on each event
   * @param filter          - Optional indexed parameter filter
   * @returns SubscriptionHandle with the subscriptionId and an unsubscribe function
   */
  async subscribeToEvents(
    contractAddress: string,
    abiEvent: AbiEventEntry,
    callback: (log: DecodedEventLog) => void,
    filter?: EventFilter
  ): Promise<SubscriptionHandle> {
    if (!this.wsProvider) {
      await this.connect();
    }
    if (!this.wsProvider) {
      throw new Error("Failed to establish WebSocket connection");
    }

    const topic0 = computeEventTopic(abiEvent);
    const indexedInputs = abiEvent.inputs.filter((i) => i.indexed);

    // Build the topics array for eth_subscribe
    const topics: (string | string[] | null)[] = [topic0];

    // Apply indexed filter: for each indexed param, if filter value provided,
    // set the topic to the exact value; otherwise null (wildcard)
    if (filter && indexedInputs.length > 0) {
      for (const inp of indexedInputs) {
        if (inp.name in filter) {
          topics.push(encodeTopicValue(inp.type, filter[inp.name]));
        } else {
          topics.push(null); // wildcard for this indexed position
        }
      }
    }

    const subId = (await this.wsProvider.send("eth_subscribe", [
      "logs",
      {
        address: contractAddress.toLowerCase(),
        topics,
      },
    ])) as string;

    const activeSub: ActiveSubscription = {
      id: subId,
      abiEvent,
      contractAddress,
      callback,
      filter,
      topic0,
    };

    this.activeSubscriptions.set(subId, activeSub);

    // Register the raw data handler
    this.wsProvider["subscriptions"].set(subId, (data: unknown) => {
      this.handleLog(activeSub, data as RawLog);
    });

    // Store resubscribe callback
    const resubCb = async () => {
      if (this.wsProvider) {
        try {
          const newSubId = (await this.wsProvider.send("eth_subscribe", [
            "logs",
            {
              address: contractAddress.toLowerCase(),
              topics,
            },
          ])) as string;

          activeSub.id = newSubId;
          this.activeSubscriptions.delete(subId);
          this.activeSubscriptions.set(newSubId, activeSub);
          this.wsProvider["subscriptions"].set(newSubId, (data: unknown) => {
            this.handleLog(activeSub, data as RawLog);
          });
        } catch (err) {
          this.emit("resubscribeError", err);
        }
      }
    };
    this.resubscribeCallbacks.push(resubCb);

    return {
      subscriptionId: subId,
      unsubscribe: async () => {
        await this.unsubscribe(subId);
      },
    };
  }

  /**
   * Unsubscribe from a specific subscription.
   */
  async unsubscribe(subscriptionId: string): Promise<void> {
    const sub = this.activeSubscriptions.get(subscriptionId);
    if (!sub) return;

    this.activeSubscriptions.delete(subscriptionId);
    if (this.wsProvider) {
      this.wsProvider["subscriptions"].delete(subscriptionId);
      try {
        await this.wsProvider.unsubscribe(subscriptionId);
      } catch {
        // Already disconnected — ignore
      }
    }
  }

  /**
   * Unsubscribe from all active subscriptions and disconnect.
   */
  async disconnect(): Promise<void> {
    for (const [id] of this.activeSubscriptions) {
      await this.unsubscribe(id);
    }
    this.resubscribeCallbacks = [];
    if (this.wsProvider) {
      this.wsProvider.disconnect();
    }
    this._connected = false;
  }

  /**
   * Check if the manager is connected.
   */
  isConnected(): boolean {
    return this._connected;
  }

  /**
   * Get the number of active subscriptions.
   */
  getActiveSubscriptionCount(): number {
    return this.activeSubscriptions.size;
  }

  // ── Private ──

  private handleLog(activeSub: ActiveSubscription, raw: RawLog): void {
    try {
      // Verify topic0 matches (guard against misrouted logs)
      if (raw.topics[0]?.toLowerCase() !== activeSub.topic0.toLowerCase()) {
        return;
      }

      // Verify contract address
      if (raw.address?.toLowerCase() !== activeSub.contractAddress.toLowerCase()) {
        return;
      }

      const args = decodeEventLog(activeSub.abiEvent, raw);

      // Apply additional indexed filter check client-side
      if (activeSub.filter) {
        const matchesFilter = Object.entries(activeSub.filter).every(
          ([key, value]) => {
            const decoded = args[key];
            if (decoded === undefined) return true;
            // Compare as lowercased hex strings for addresses, bigints for numbers
            if (typeof value === "string" && typeof decoded === "string") {
              return decoded.toLowerCase() === value.toLowerCase();
            }
            return decoded === value;
          }
        );
        if (!matchesFilter) return;
      }

      const decoded: DecodedEventLog = {
        event: activeSub.abiEvent.name,
        address: raw.address,
        blockNumber: raw.blockNumber ? parseInt(raw.blockNumber, 16) : null,
        transactionHash: raw.transactionHash ?? null,
        logIndex: raw.logIndex ? parseInt(raw.logIndex, 16) : null,
        args,
        raw,
      };

      activeSub.callback(decoded);
      this.emit("event", decoded);
    } catch (err) {
      this.emit("decodeError", err);
    }
  }

  private async resubscribeAll(): Promise<void> {
    this.emit("resubscribing");
    for (const cb of this.resubscribeCallbacks) {
      try {
        await cb();
      } catch (err) {
        this.emit("resubscribeError", err);
      }
    }
    this.emit("resubscribed");
  }
}

/**
 * Encode a filter value into a 32-byte hex topic value.
 */
function encodeTopicValue(
  type: string,
  value: string | number | bigint | boolean
): string {
  if (type === "address") {
    const addr = typeof value === "string" ? value.toLowerCase() : String(value);
    const cleaned = addr.startsWith("0x") ? addr.slice(2) : addr;
    return "0x" + cleaned.padStart(64, "0");
  }
  if (type === "bool") {
    return "0x" + (value ? "1" : "0").padStart(64, "0");
  }
  if (type.startsWith("uint") || type.startsWith("int")) {
    const n = BigInt(value as string | number | bigint);
    return "0x" + n.toString(16).padStart(64, "0");
  }
  if (type === "bytes32") {
    const s = typeof value === "string" ? value : String(value);
    const cleaned = s.startsWith("0x") ? s.slice(2) : s;
    return "0x" + cleaned.padEnd(64, "0");
  }
  if (type === "string" || type === "bytes") {
    // Dynamic types: topic holds keccak256 hash
    const s = typeof value === "string" ? value : String(value);
    return "0x" + keccak256Hex(s);
  }
  // Fallback
  const s = String(value);
  return "0x" + (s.startsWith("0x") ? s.slice(2) : s).padStart(64, "0");
}
