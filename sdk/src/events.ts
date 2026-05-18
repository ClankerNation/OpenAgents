/**
 * Event subscription and decoding module for OpenAgentsSDK.
 *
 * Provides real-time event subscription via WebSocket with automatic
 * reconnection, ABI-based log decoding, and indexed parameter filtering.
 *
 * Agent: hermes | OS: Linux 6.14.0-37-generic | Arch: x86_64
 * Home: /home/ubuntu | CWD: /home/ubuntu/.hermes/hermes-agent | Shell: /bin/bash
 */

import { ethers } from "ethers";

/** Filter parameters for narrowing event subscriptions by indexed args */
export interface EventFilter {
  indexed?: Record<string, string | string[]>;
}

/** Decoded event log with named parameters */
export interface DecodedEvent {
  eventName: string;
  args: Record<string, unknown>;
  blockNumber: number;
  transactionHash: string;
  logIndex: number;
  address: string;
}

/** Subscription handle for managing active event subscriptions */
export interface EventSubscription {
  id: symbol;
  contract: string;
  eventName: string;
  filter?: EventFilter;
  active: boolean;
}

type EventCallback = (event: DecodedEvent) => void;

/** Configuration for WebSocket-based event subscriptions */
export interface EventSubscriberConfig {
  wsUrl: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}

interface SubscriptionEntry {
  contract: string;
  eventName: string;
  filter?: EventFilter;
  iface: ethers.Interface;
  callback: EventCallback;
}

/**
 * EventSubscriber provides real-time event subscription with ABI decoding,
 * indexed parameter filtering, and automatic WebSocket reconnection.
 *
 * On reconnect, all active subscriptions are automatically re-established.
 */
export class EventSubscriber {
  private wsProvider: ethers.WebSocketProvider | null = null;
  private config: EventSubscriberConfig;
  private subscriptions = new Map<symbol, SubscriptionEntry>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectCount = 0;
  private connected = false;

  constructor(config: EventSubscriberConfig) {
    this.config = config;
  }

  /** Establish a WebSocket connection for event subscriptions. */
  async connect(): Promise<void> {
    await this.initWsProvider();
  }

  /** Initialize or reinitialize the WebSocket provider with reconnect handling. */
  private async initWsProvider(): Promise<void> {
    if (this.wsProvider) {
      try { this.wsProvider.destroy(); } catch { /* ignore */ }
    }

    this.wsProvider = new ethers.WebSocketProvider(this.config.wsUrl);

    // Detect connection ready
    await this.wsProvider.getNetwork();

    this.wsProvider.on("error", () => {
      this.scheduleReconnect();
    });

    this.wsProvider.on("close", () => {
      this.connected = false;
      this.scheduleReconnect();
    });

    this.connected = true;
    this.reconnectCount = 0;

    // Re-subscribe all existing subscriptions after connect/reconnect
    await this.resubscribeAll();
  }

  /** Schedule a reconnection attempt with exponential backoff. */
  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;

    const maxAttempts = this.config.maxReconnectAttempts ?? 10;
    if (this.reconnectCount >= maxAttempts) {
      console.error("Max reconnect attempts reached. Giving up.");
      return;
    }

    const interval = this.config.reconnectIntervalMs ?? 3000;
    const delay = Math.min(interval * Math.pow(2, this.reconnectCount), 60000);

    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null;
      this.reconnectCount++;
      try {
        await this.initWsProvider();
      } catch {
        // Will retry via scheduleReconnect on next error
      }
    }, delay);
  }

  /**
   * Subscribe to a specific event on a contract with ABI decoding.
   *
   * @param contractAddress - On-chain contract address to monitor
   * @param abi - Contract ABI fragments for event decoding
   * @param eventName - The specific event name to subscribe to
   * @param callback - Called with each decoded event
   * @param filter - Optional filter for indexed parameters
   * @returns Subscription handle for later unsubscription
   */
  async subscribeToEvents(
    contractAddress: string,
    abi: ethers.Fragment | ethers.Fragment[] | string | string[],
    eventName: string,
    callback: EventCallback,
    filter?: EventFilter
  ): Promise<EventSubscription> {
    if (!this.wsProvider) {
      throw new Error("EventSubscriber not connected — call connect() first");
    }

    const iface = Array.isArray(abi) || typeof abi === "string"
      ? new ethers.Interface(abi as string[])
      : new ethers.Interface([abi as ethers.Fragment]);

    const eventFragment = iface.getEvent(eventName);
    if (!eventFragment) {
      throw new Error(`Event "${eventName}" not found in ABI`);
    }

    const subscriptionId = Symbol(`sub:${contractAddress}:${eventName}`);
    const contract = new ethers.Contract(contractAddress, iface, this.wsProvider);

    // Build topic filter for indexed parameters
    const topicFilter = this.buildTopicFilter(contractAddress, iface, eventName, filter);

    // Register ethers.js event listener
    contract.on(topicFilter, (...args: unknown[]) => {
      const eventLog = args[args.length - 1] as ethers.Log | undefined;
      const decoded = this.decodeEventArgs(eventName, iface, args);
      if (decoded) {
        callback(decoded);
      }
    });

    this.subscriptions.set(subscriptionId, {
      contract: contractAddress,
      eventName,
      filter,
      iface,
      callback,
    });

    return {
      id: subscriptionId,
      contract: contractAddress,
      eventName,
      filter,
      active: true,
    };
  }

  /**
   * Subscribe to all events from a contract address (wildcard).
   *
   * @param contractAddress - Address to monitor
   * @param abi - ABI fragments for decoding all events
   * @param callback - Called for each decoded event
   * @returns Subscription handle
   */
  async subscribeLogs(
    contractAddress: string,
    abi: ethers.Fragment | ethers.Fragment[] | string | string[],
    callback: EventCallback
  ): Promise<EventSubscription> {
    if (!this.wsProvider) {
      throw new Error("EventSubscriber not connected — call connect() first");
    }

    const iface = Array.isArray(abi) || typeof abi === "string"
      ? new ethers.Interface(abi as string[])
      : new ethers.Interface([abi as ethers.Fragment]);

    const subscriptionId = Symbol(`sub:${contractAddress}:*`);
    const contract = new ethers.Contract(contractAddress, iface, this.wsProvider);

    contract.on("*", (log: ethers.Log) => {
      try {
        const parsed = iface.parseLog({ topics: log.topics as string[], data: log.data });
        if (!parsed) return;

        const args: Record<string, unknown> = {};
        parsed.fragment.inputs.forEach((input, i) => {
          args[input.name] = parsed!.args[i];
        });

        callback({
          eventName: parsed.name,
          args,
          blockNumber: log.blockNumber ?? 0,
          transactionHash: log.transactionHash ?? "",
          logIndex: log.index ?? 0,
          address: contractAddress,
        });
      } catch {
        // Skip logs that can't be decoded with this ABI
      }
    });

    this.subscriptions.set(subscriptionId, {
      contract: contractAddress,
      eventName: "*",
      iface,
      callback,
    });

    return {
      id: subscriptionId,
      contract: contractAddress,
      eventName: "*",
      active: true,
    };
  }

  /** Convenience shorthand for subscribeToEvents. */
  async onEvent(
    contractAddress: string,
    abi: ethers.Fragment | ethers.Fragment[] | string | string[],
    eventName: string,
    callback: EventCallback,
    filter?: EventFilter
  ): Promise<EventSubscription> {
    return this.subscribeToEvents(contractAddress, abi, eventName, callback, filter);
  }

  /** Unsubscribe from an active event subscription. */
  unsubscribe(subscription: EventSubscription): void {
    const entry = this.subscriptions.get(subscription.id);
    if (entry && this.wsProvider) {
      const contract = new ethers.Contract(entry.contract, entry.iface, this.wsProvider);
      if (entry.eventName === "*") {
        contract.removeAllListeners();
      } else {
        contract.off(entry.eventName, () => {});
      }
      subscription.active = false;
      this.subscriptions.delete(subscription.id);
    }
  }

  /** Disconnect from the WebSocket and clear all subscriptions. */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.subscriptions.clear();
    this.wsProvider?.destroy();
    this.wsProvider = null;
    this.connected = false;
  }

  /** Whether the WebSocket is currently connected. */
  isConnected(): boolean {
    return this.connected && this.wsProvider !== null;
  }

  /**
   * Build an ethers.js EventFilter from contract address, event name, and indexed params.
   */
  private buildTopicFilter(
    contractAddress: string,
    iface: ethers.Interface,
    eventName: string,
    filter?: EventFilter
  ): ethers.EventFilter {
    const eventFragment = iface.getEvent(eventName)!;
    const indexedInputs = eventFragment.inputs.filter((input) => input.indexed);

    // Build topic args matching ethers.js filter convention
    const topicArgs: (string | string[] | null)[] = [];

    if (filter?.indexed) {
      for (const indexedInput of indexedInputs) {
        const value = filter.indexed[indexedInput.name];
        if (value !== undefined) {
          topicArgs.push(value);
        } else {
          topicArgs.push(null);
        }
      }
    }

    return {
      address: contractAddress,
      topics: [
        eventFragment.topicHash,
        ...topicArgs,
      ],
    };
  }

  /**
   * Decode ethers.js event callback arguments into a DecodedEvent.
   */
  private decodeEventArgs(
    eventName: string,
    iface: ethers.Interface,
    args: unknown[]
  ): DecodedEvent | null {
    try {
      // ethers v6 contract event listeners pass (..args, EventLog) as arguments
      const eventLog = args[args.length - 1] as any;
      if (!eventLog || typeof eventLog !== "object") return null;

      const namedArgs: Record<string, unknown> = {};
      const inputs = iface.getEvent(eventName)?.inputs ?? [];

      // Named arguments come before the EventLog in the callback args
      inputs.forEach((input, i) => {
        if (i < args.length - 1) {
          namedArgs[input.name] = args[i];
        }
      });

      return {
        eventName,
        args: namedArgs,
        blockNumber: eventLog?.blockNumber ?? 0,
        transactionHash: eventLog?.transactionHash ?? "",
        logIndex: eventLog?.index ?? eventLog?.logIndex ?? 0,
        address: eventLog?.address ?? "",
      };
    } catch {
      return null;
    }
  }

  /** Re-subscribe all tracked subscriptions after a WebSocket reconnect. */
  private async resubscribeAll(): Promise<void> {
    if (!this.wsProvider) return;
    this.connected = true;

    for (const [, sub] of this.subscriptions) {
      try {
        const contract = new ethers.Contract(sub.contract, sub.iface, this.wsProvider!);

        if (sub.eventName === "*") {
          contract.on("*", (log: ethers.Log) => {
            try {
              const parsed = sub.iface.parseLog({ topics: log.topics as string[], data: log.data });
              if (!parsed) return;

              const args: Record<string, unknown> = {};
              parsed.fragment.inputs.forEach((input, i) => {
                args[input.name] = parsed!.args[i];
              });

              sub.callback({
                eventName: parsed.name,
                args,
                blockNumber: log.blockNumber ?? 0,
                transactionHash: log.transactionHash ?? "",
                logIndex: log.index ?? 0,
                address: sub.contract,
              });
            } catch { /* skip undecodable logs */ }
          });
        } else {
          const topicFilter = this.buildTopicFilter(sub.contract, sub.iface, sub.eventName, sub.filter);
          contract.on(topicFilter, (...args: unknown[]) => {
            const decoded = this.decodeEventArgs(sub.eventName, sub.iface, args);
            if (decoded) sub.callback(decoded);
          });
        }
      } catch (err) {
        console.error(`Failed to resubscribe to ${sub.eventName} on ${sub.contract}:`, err);
      }
    }
  }
}
