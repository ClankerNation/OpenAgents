/**
 * @contributor-info rafaio1
 * @session-init Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for event subscription and decoding (Issue #196)
 * @os linux
 * @arch x64
 * @home /root
 * @workdir /tmp/openagents_issue_196
 * @shell /bin/bash
 */
import { ethers } from "ethers";

/** Decoded event log with named parameters. */
export interface DecodedEvent {
  readonly name: string;
  readonly args: Record<string, unknown>;
  readonly blockNumber: number;
  readonly transactionHash: string;
  readonly logIndex: number;
}

/** Filter criteria for indexed event parameters. */
export interface EventFilter {
  [paramName: string]: string | number | bigint | boolean | null;
}

/** Configuration for event subscription reconnection behavior. */
export interface SubscriptionOptions {
  /** Maximum reconnection attempts before giving up. Default: Infinity */
  maxReconnectAttempts?: number;
  /** Delay in ms between reconnection attempts. Default: 3000 */
  reconnectDelayMs?: number;
}

/**
 * Subscribes to contract events via WebSocket with automatic reconnection
 * and ABI-based log decoding.
 *
 * @param wsUrl - WebSocket RPC endpoint URL
 * @param contractAddress - Target contract address
 * @param abi - Contract ABI (human-readable or JSON format)
 * @param eventName - Name of the event to subscribe to
 * @param callback - Invoked for each decoded event
 * @param filter - Optional indexed parameter filters
 * @param options - Reconnection configuration
 * @returns Unsubscribe function that cleans up all listeners
 */
export function subscribeToEvents(
  wsUrl: string,
  contractAddress: string,
  abi: ethers.InterfaceAbi,
  eventName: string,
  callback: (event: DecodedEvent) => void,
  filter: EventFilter = {},
  options: SubscriptionOptions = {},
): () => void {
  const maxAttempts = options.maxReconnectAttempts ?? Infinity;
  const reconnectDelay = options.reconnectDelayMs ?? 3000;

  let disposed = false;
  let currentProvider: ethers.WebSocketProvider | null = null;
  let attemptCount = 0;

  const iface = new ethers.Interface(abi);
  const eventFragment = iface.getEvent(eventName);
  if (!eventFragment) {
    throw new Error(`Event "${eventName}" not found in provided ABI`);
  }

  // Build filter topics from indexed parameters
  const buildTopics = (): (string | string[] | null)[] => {
    const topics: (string | string[] | null)[] = [iface.getEventTopic(eventFragment)];
    for (let i = 0; i < eventFragment.inputs.length; i++) {
      const input = eventFragment.inputs[i];
      if (!input.indexed) continue;
      const value = filter[input.name];
      if (value === undefined || value === null) {
        topics.push(null);
      } else {
        topics.push(ethers.id(String(value)));
      }
    }
    return topics;
  };

  const connect = (): void => {
    if (disposed) return;

    currentProvider = new ethers.WebSocketProvider(wsUrl);

    currentProvider.websocket.on("open", () => {
      attemptCount = 0;
    });

    currentProvider.websocket.on("close", () => {
      if (disposed) return;
      attemptCount++;
      if (attemptCount <= maxAttempts) {
        setTimeout(connect, reconnectDelay);
      }
    });

    currentProvider.websocket.on("error", () => {
      // close handler will trigger reconnect
    });

    const topics = buildTopics();
    const filterObj: ethers.Filter = {
      address: contractAddress,
      topics,
    };

    currentProvider.on(filterObj, (log: ethers.Log) => {
      try {
        const parsed = iface.parseLog({ topics: log.topics as string[], data: log.data });
        if (!parsed) return;

        const args: Record<string, unknown> = {};
        for (const key of Object.keys(parsed.fragment.inputs)) {
          args[key] = parsed.args[key];
        }

        const decoded: DecodedEvent = Object.freeze({
          name: parsed.name,
          args: Object.freeze(args),
          blockNumber: log.blockNumber,
          transactionHash: log.transactionHash,
          logIndex: log.index,
        });

        callback(decoded);
      } catch {
        // Skip malformed logs silently — do not crash the subscription
      }
    });
  };

  connect();

  // Return unsubscribe function
  return () => {
    disposed = true;
    if (currentProvider) {
      currentProvider.removeAllListeners();
      currentProvider.destroy();
      currentProvider = null;
    }
  };
}
