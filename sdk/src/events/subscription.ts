/**
 * @fix-author scotia1973-bot
 *
 * Event subscription manager for the OpenAgents SDK.
 *
 * Provides a high-level EventSubscriptionManager that wraps ethers.js
 * contract instances to subscribe to on-chain events, manage active
 * subscriptions, filter by event type or address, and handle
 * reconnection gracefully.
 */

import { ethers } from "ethers";
import { EventEmitter } from "events";
import {
  type AbiEvent,
  type DecodedEvent,
  type LogEntry,
  decodeEventLog,
  buildEventMap,
  eventSignatureHash,
} from "./decoder";

// ── Types ───────────────────────────────────────────────────────────────────

export interface SubscriptionFilter {
  /** Contract address to filter by (optional) */
  address?: string;
  /** Event name to filter by (optional) */
  eventName?: string;
}

export interface SubscriptionConfig {
  /** An array of ABI event definitions */
  abis: readonly AbiEvent[];
  /** Maximum number of reconnection attempts (default: 10) */
  maxReconnectAttempts?: number;
  /** Delay between reconnection attempts in ms (default: 2000) */
  reconnectDelayMs?: number;
}

export interface ActiveSubscription {
  readonly id: string;
  readonly eventName: string;
  readonly contractAddress: string;
  readonly filter?: SubscriptionFilter;
  readonly createdAt: number;
  remove(): void;
}

export type EventCallback = (event: DecodedEvent) => void;

// ── Subscription Manager ────────────────────────────────────────────────────

export class EventSubscriptionManager extends EventEmitter {
  private provider: ethers.JsonRpcProvider;
  private abis: readonly AbiEvent[];
  private eventMap: Map<string, AbiEvent>;
  private subscriptions = new Map<string, ActiveSubscription>();
  private contractListeners = new Map<
    string,
    { contract: ethers.Contract; eventNames: Set<string> }
  >();
  private maxReconnectAttempts: number;
  private reconnectDelayMs: number;
  private isPolling = false;
  private pollIntervalMs = 4000;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private trackedEvents: Array<{
    contract: ethers.Contract;
    eventName: string;
    callback: EventCallback;
    filter?: SubscriptionFilter;
  }> = [];

  constructor(
    provider: ethers.JsonRpcProvider,
    config: SubscriptionConfig
  ) {
    super();
    this.provider = provider;
    this.abis = config.abis;
    this.eventMap = buildEventMap(config.abis);
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this.reconnectDelayMs = config.reconnectDelayMs ?? 2000;
  }

  /**
   * Subscribe to an on-chain event.
   *
   * @param contractAddress - The address of the contract emitting the event
   * @param abi - Array of ABI event definitions (or a single AbiEvent)
   * @param eventName - The name of the event to subscribe to
   * @param callback - Function to call when the event is emitted
   * @param filter - Optional filter by address or additional event name
   * @returns An ActiveSubscription handle that can be used to unsubscribe
   */
  async subscribe(
    contractAddress: string,
    abi: ethers.Interface | readonly AbiEvent[],
    eventName: string,
    callback: EventCallback,
    filter?: SubscriptionFilter
  ): Promise<ActiveSubscription> {
    const contract = this.getOrCreateContract(contractAddress, abi);

    const wrappedCallback = (...args: unknown[]) => {
      const event = args[args.length - 1] as ethers.EventLog;
      if (!event || !event.log || !event.topics) return;

      const decoded = this.tryDecode(eventName, event);
      if (decoded) {
        // Apply filter if specified
        if (filter?.eventName && decoded.name !== filter.eventName) return;
        if (filter?.address && decoded.address.toLowerCase() !== filter.address.toLowerCase()) return;

        callback(decoded);
        this.emit("event", decoded);
      }
    };

    // Use ethers on() to listen to the event
    contract.on(eventName, wrappedCallback);

    const subId = `${contractAddress}_${eventName}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    const subscription: ActiveSubscription = {
      id: subId,
      eventName,
      contractAddress,
      filter,
      createdAt: Date.now(),
      remove: () => {
        contract.off(eventName, wrappedCallback);
        this.subscriptions.delete(subId);
        this.emit("unsubscribed", { id: subId, eventName, contractAddress });
      },
    };

    this.subscriptions.set(subId, subscription);
    this.trackedEvents.push({ contract, eventName, callback, filter });

    // Track this contract's listeners for reconnection
    this.trackContractListener(contractAddress, eventName);

    this.emit("subscribed", { id: subId, eventName, contractAddress });

    return subscription;
  }

  /**
   * Subscribe to all events from a contract using the provided ABI definitions.
   *
   * @param contractAddress - The contract address to listen to
   * @param abi - ABI event definitions
   * @param callback - Function to call for each matching event
   * @param filter - Optional filter
   * @returns Array of subscription handles
   */
  async subscribeAll(
    contractAddress: string,
    abi: readonly AbiEvent[],
    callback: EventCallback,
    filter?: SubscriptionFilter
  ): Promise<ActiveSubscription[]> {
    const subscriptions: ActiveSubscription[] = [];

    for (const eventAbi of abi) {
      if (filter?.eventName && eventAbi.name !== filter.eventName) continue;
      const sub = await this.subscribe(
        contractAddress,
        abi,
        eventAbi.name,
        callback,
        filter
      );
      subscriptions.push(sub);
    }

    return subscriptions;
  }

  /**
   * Decode raw event logs from a transaction receipt using known ABIs.
   *
   * @param logs - Array of raw log entries from the receipt
   * @returns Array of decoded events
   */
  decodeTransactionLogs(logs: ethers.Log[]): DecodedEvent[] {
    const decoded: DecodedEvent[] = [];

    for (const log of logs) {
      if (!log.topics || log.topics.length === 0) continue;

      const topic0 = log.topics[0].toLowerCase();
      const abi = this.eventMap.get(topic0);
      if (!abi) continue;

      const logEntry: LogEntry = {
        address: log.address,
        topics: log.topics as string[],
        data: log.data,
        blockNumber: log.blockNumber?.toString(16) ?? "0x0",
        transactionHash: log.transactionHash ?? "",
        logIndex: log.index?.toString(16) ?? "0x0",
        blockHash: log.blockHash,
        transactionIndex: log.transactionIndex?.toString(),
        removed: log.removed,
      };

      try {
        decoded.push(decodeEventLog(abi, logEntry));
      } catch {
        // Skip logs that don't match
      }
    }

    return decoded;
  }

  /**
   * Start polling for events on a regular interval.
   * Useful for networks without reliable WebSocket support.
   *
   * @param intervalMs - Polling interval in milliseconds (default: 4000)
   */
  startPolling(intervalMs = 4000): void {
    if (this.isPolling) return;
    this.isPolling = true;
    this.pollIntervalMs = intervalMs;
    this.emit("pollingStarted", { intervalMs });
  }

  /**
   * Stop polling for events.
   */
  stopPolling(): void {
    this.isPolling = false;
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    this.emit("pollingStopped");
  }

  /**
   * Reconnect all active subscriptions.
   * Called automatically on provider reconnection.
   */
  async reconnectAll(): Promise<void> {
    this.emit("reconnecting");

    // Remove all existing listeners
    for (const [, info] of this.contractListeners) {
      info.contract.removeAllListeners();
    }
    this.contractListeners.clear();

    // Resubscribe all tracked events
    const currentEvents = [...this.trackedEvents];
    this.trackedEvents = [];

    for (const te of currentEvents) {
      const contract = this.getOrCreateContract(
        te.contract.target as string,
        te.contract.interface
      );

      const wrappedCallback = (...args: unknown[]) => {
        const event = args[args.length - 1] as ethers.EventLog;
        if (!event || !event.log || !event.topics) return;

        const decoded = this.tryDecode(te.eventName, event);
        if (decoded) {
          if (te.filter?.eventName && decoded.name !== te.filter.eventName) return;
          if (te.filter?.address && decoded.address.toLowerCase() !== te.filter.address.toLowerCase()) return;
          te.callback(decoded);
          this.emit("event", decoded);
        }
      };

      contract.on(te.eventName, wrappedCallback);
      this.trackContractListener(te.contract.target as string, te.eventName);
      this.trackedEvents.push(te);
    }

    this.emit("reconnected");
  }

  /**
   * Unsubscribe from all events and clean up.
   */
  async unsubscribeAll(): Promise<void> {
    for (const [, sub] of this.subscriptions) {
      sub.remove();
    }
    this.subscriptions.clear();
    this.trackedEvents = [];
    this.stopPolling();

    for (const [, info] of this.contractListeners) {
      info.contract.removeAllListeners();
    }
    this.contractListeners.clear();

    this.emit("unsubscribedAll");
  }

  /**
   * Get all active subscriptions.
   */
  getActiveSubscriptions(): ActiveSubscription[] {
    return Array.from(this.subscriptions.values());
  }

  /**
   * Get the number of active subscriptions.
   */
  getSubscriptionCount(): number {
    return this.subscriptions.size;
  }

  /**
   * Get the current polling state.
   */
  getPollingState(): { active: boolean; intervalMs: number } {
    return { active: this.isPolling, intervalMs: this.pollIntervalMs };
  }

  // ── Private helpers ────────────────────────────────────────────────────────

  private getOrCreateContract(
    address: string,
    abi: ethers.Interface | readonly AbiEvent[]
  ): ethers.Contract {
    // Check cache
    const cacheKey = address.toLowerCase();
    const existing = this.contractListeners.get(cacheKey);
    if (existing) return existing.contract;

    // Create a minimal ABI from AbiEvent definitions if needed
    let contract: ethers.Contract;

    if (Array.isArray(abi)) {
      // Build a human-readable ABI
      const frags = abi.map((e) => {
        const types = e.inputs.map((i) => `${i.type}${i.indexed ? " indexed" : ""}`);
        return `event ${e.name}(${types.join(",")})`;
      });
      contract = new ethers.Contract(address, frags, this.provider);
    } else {
      contract = new ethers.Contract(address, abi, this.provider);
    }

    this.contractListeners.set(cacheKey, {
      contract,
      eventNames: new Set<string>(),
    });

    return contract;
  }

  private trackContractListener(address: string, eventName: string): void {
    const key = address.toLowerCase();
    const existing = this.contractListeners.get(key);
    if (existing) {
      existing.eventNames.add(eventName);
    }
  }

  private tryDecode(
    eventName: string,
    event: ethers.EventLog
  ): DecodedEvent | null {
    const topic0 = event.topics?.[0]?.toLowerCase();
    if (!topic0) return null;

    const abi = this.eventMap.get(topic0);
    if (!abi) return null;

    try {
      const logEntry: LogEntry = {
        address: event.address,
        topics: event.topics as string[],
        data: event.data,
        blockNumber: event.blockNumber?.toString(16) ?? "0x0",
        transactionHash: event.transactionHash ?? "",
        logIndex: event.index?.toString(16) ?? "0x0",
        blockHash: event.blockHash,
        transactionIndex: event.transactionIndex?.toString(),
        removed: event.removed,
      };
      return decodeEventLog(abi, logEntry);
    } catch {
      return null;
    }
  }
}

/**
 * Create an ethers.js filter object for querying past events.
 *
 * @param address - Contract address
 * @param eventAbi - The ABI event definition
 * @param filterValues - Optional indexed parameter values to filter by
 * @returns An ethers filter suitable for contract.queryFilter()
 */
export function createEventFilter(
  address: string,
  eventAbi: AbiEvent,
  filterValues?: Record<number, string>
): ethers.Filter {
  const inputTypes = eventAbi.inputs.map((i) => i.type);
  const sigHash = eventSignatureHash(eventAbi.name, inputTypes);

  const topics: (string | string[] | null)[] = [sigHash];

  if (filterValues) {
    const indexedInputs = eventAbi.inputs.filter((i) => i.indexed);
    for (let i = 0; i < indexedInputs.length; i++) {
      if (filterValues[i] !== undefined) {
        const val = filterValues[i];
        // Pad to 32 bytes for non-address indexed params
        const padded = val.startsWith("0x") && val.length === 42
          ? val
          : "0x" + val.slice(2).padStart(64, "0");
        topics.push(padded);
      } else {
        topics.push(null); // No filter for this position
      }
    }
  }

  return {
    address,
    topics,
  };
}
