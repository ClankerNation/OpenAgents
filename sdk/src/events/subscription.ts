/**
 * Event subscription and decoding for OpenAgentsSDK.
 *
 * @fix-author Gaotax2006
 * @date 2026-06-23
 * @issue #144 Add event subscription and decoding to OpenAgentsSDK
 */

import { ethers } from "ethers";

export interface DecodedEvent {
  name: string;
  args: Record<string, unknown>;
  blockNumber: number;
  transactionHash: string;
  logIndex: number;
  topic: string;
}

export interface SubscriptionHandle {
  subscriptionId: string;
  eventName: string;
  callback: (event: DecodedEvent) => void;
  unsubscribe: () => Promise<boolean>;
}

/**
 * Create an event decoder from contract ABI and event name.
 * @param abi Contract ABI array
 * @param eventName Event name to decode (e.g., "Deposited")
 * @returns Function that decodes log topics + data into typed args
 */
export function createEventDecoder(
  abi: unknown[],
  eventName: string
): (topics: string[], data: string) => Record<string, unknown> {
  const iface = new ethers.Interface(abi as ethers.AbigenOutput[]);
  const eventFragment = iface.fragments.find(
    (f) => f.type === "event" && f.name === eventName
  );

  if (!eventFragment) {
    throw new Error(`Event "${eventName}" not found in ABI`);
  }

  const event = ethers.EventFragment.from(eventFragment);
  const topic = ethers.id(event.format!("full"));

  return (topics: string[], data: string): Record<string, unknown> => {
    return iface.decodeEventLog(event, data, topics);
  };
}

/**
 * Subscribe to contract events with automatic decoding.
 * @param provider ethers Provider (ethers v6)
 * @param contractAddress Contract address to watch
 * @param abi Contract ABI
 * @param eventName Event name to subscribe to
 * @param callback Called with decoded events
 * @param fromBlock Optional starting block number (defaults to "latest")
 * @returns SubscriptionHandle for cleanup
 */
export async function subscribeToEvent(
  provider: ethers.Provider,
  contractAddress: string,
  abi: unknown[],
  eventName: string,
  callback: (event: DecodedEvent) => void,
  fromBlock: number | "latest" = "latest"
): Promise<SubscriptionHandle> {
  const iface = new ethers.Interface(abi as ethers.AbigenOutput[]);
  const eventFragment = iface.fragments.find(
    (f) => f.type === "event" && f.name === eventName
  );

  if (!eventFragment) {
    throw new Error(`Event "${eventName}" not found in ABI`);
  }

  const event = ethers.EventFragment.from(eventFragment);
  const topic = ethers.id(event.format("full"));

  // Subscribe via eth_subscribe (WebSocket)
  const wsProvider = provider as ethers.WebSocketProvider;
  if (wsProvider._isWebSocketProvider) {
    const subId = await wsProvider.send("eth_subscribe", ["logs", {
      address: contractAddress.toLowerCase(),
      topics: [topic],
    }]);

    const listener = (payload: string) => {
      const data = JSON.parse(payload);
      if (data.params?.subscription === subId && data.params?.result) {
        const log = data.params.result;
        try {
          const decoded = iface.decodeLog(log.topics as string[], log.data as string, log.topics as string[]);
          callback({
            name: eventName,
            args: Object.fromEntries(event.inputs.map((input, i) => [input.name || `_${i}`, decoded[i]])),
            blockNumber: parseInt(log.blockNumber || "0", 16),
            transactionHash: log.transactionHash || "",
            logIndex: parseInt(log.logIndex || "0", 16),
            topic: topic,
          });
        } catch {
          // Skip malformed events
        }
      }
    };

    wsProvider.on("message", listener);

    return {
      subscriptionId: subId,
      eventName,
      callback,
      unsubscribe: async () => {
        wsProvider.off("message", listener);
        return wsProvider.send("eth_unsubscribe", [subId]);
      },
    };
  }

  // Fallback: poll via event filter
  const filter = provider.createFilter({
    address: contractAddress.toLowerCase(),
    topics: [topic],
  });

  let lastBlock = typeof fromBlock === "number" ? fromBlock : await provider.getBlockNumber();

  const pollInterval = setInterval(async () => {
    const logs = await provider.getLogs({
      address: contractAddress.toLowerCase(),
      topics: [topic],
      fromBlock: lastBlock + 1,
      toBlock: "latest",
    });

    for (const log of logs) {
      try {
        const decoded = iface.decodeLog(log.topics as string[], log.data as string, log.topics as string[]);
        callback({
          name: eventName,
          args: Object.fromEntries(event.inputs.map((input, i) => [input.name || `_${i}`, decoded[i]])),
          blockNumber: log.blockNumber,
          transactionHash: log.transactionHash,
          logIndex: log.logIndex,
          topic: topic,
        });
      } catch {
        // Skip malformed events
      }
    }

    if (logs.length > 0) {
      lastBlock = logs[logs.length - 1].blockNumber;
    }
  }, 3000);

  return {
    subscriptionId: "poll:" + contractAddress + ":" + eventName,
    eventName,
    callback,
    unsubscribe: async () => {
      clearInterval(pollInterval);
      return true;
    },
  };
}

/**
 * Decode historical events from a contract.
 * @param provider ethers Provider
 * @param contractAddress Contract address
 * @param abi Contract ABI
 * @param eventName Event name
 * @param fromBlock Starting block
 * @param toBlock Ending block (defaults to "latest")
 * @returns Array of decoded events
 */
export async function decodeHistoricalEvents(
  provider: ethers.Provider,
  contractAddress: string,
  abi: unknown[],
  eventName: string,
  fromBlock: number,
  toBlock: number | "latest" = "latest"
): Promise<DecodedEvent[]> {
  const iface = new ethers.Interface(abi as ethers.AbigenOutput[]);
  const eventFragment = iface.fragments.find(
    (f) => f.type === "event" && f.name === eventName
  );

  if (!eventFragment) {
    throw new Error(`Event "${eventName}" not found in ABI`);
  }

  const event = ethers.EventFragment.from(eventFragment);
  const topic = ethers.id(event.format("full"));

  const logs = await provider.getLogs({
    address: contractAddress.toLowerCase(),
    topics: [topic],
    fromBlock,
    toBlock,
  });

  return logs.map((log) => {
    try {
      const decoded = iface.decodeLog(log.topics as string[], log.data as string, log.topics as string[]);
      return {
        name: eventName,
        args: Object.fromEntries(event.inputs.map((input, i) => [input.name || `_${i}`, decoded[i]])),
        blockNumber: log.blockNumber,
        transactionHash: log.transactionHash,
        logIndex: log.logIndex,
        topic,
      };
    } catch {
      return {
        name: eventName,
        args: {},
        blockNumber: log.blockNumber,
        transactionHash: log.transactionHash,
        logIndex: log.logIndex,
        topic,
      };
    }
  });
}
