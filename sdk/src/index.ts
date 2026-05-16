/**
 * OpenAgents SDK — Decentralized AI Agent Orchestration Protocol
 *
 * Contributor Trace:
 *   Agent: Metatron (Hermes AI celestial scribe)
 *   Platform: Hermes Agent / DeepSeek V4 Pro
 *   ISO Timestamp: 2026-05-16T21:45:00Z
 *   OS: linux, arch: x86_64, home: /home/power, cwd: /home/power/projects/OpenAgents, shell: bash
 *   Startup Instructions: You are Metatron's autonomous bounty-hunting loop. You wake up every
 *     30 minutes to generate income. Check status of all open PRs, fix review-blocked PRs first,
 *     then work on the highest-priority unclaimed bounty. Prefer Solidity issues. Stay in
 *     /home/power/projects/OpenAgents as workdir.
 */

import { ethers } from "ethers";
import { WebSocketProvider, WsProviderConfig } from "./providers/websocket";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
  wsUrl?: string;
}

export interface EventFilter {
  /** Contract address to listen to */
  address: string;
  /** Optional topic filters (null = wildcard for that position) */
  topics?: (string | null)[];
}

export interface DecodedEvent {
  /** Human-readable event name (e.g., "Transfer") */
  name: string;
  /** Full event signature (e.g., "Transfer(address,address,uint256)") */
  signature: string;
  /** Decoded named arguments */
  args: Record<string, unknown>;
  /** Raw log object from the provider */
  log: ethers.Log;
}

export interface SubscribeResult {
  /** The eth_subscribe subscription ID */
  subscriptionId: string;
  /** The WebSocket provider for lifecycle management */
  wsProvider: WebSocketProvider;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = new ethers.JsonRpcProvider(config.rpcUrl);
    this.signer = new ethers.Wallet(config.privateKey, this.provider);
  }

  async registerAgent(): Promise<string> {
    const registry = new ethers.Contract(
      this.config.registryAddress,
      ["function registerAgent(string,string) payable returns (bytes32)"],
      this.signer
    );

    const fee = await registry.registrationFee();
    const tx = await registry.registerAgent(
      this.config.name,
      this.config.endpoint,
      { value: fee }
    );
    const receipt = await tx.wait();
    return receipt.logs[0].topics[1];
  }

  async claimTask(taskId: number, agentId: string): Promise<void> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function assignTask(uint256,bytes32)"],
      this.signer
    );
    const tx = await router.assignTask(taskId, agentId);
    await tx.wait();
  }

  async submitResult(taskId: number, result: string): Promise<void> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function completeTask(uint256,bytes)"],
      this.signer
    );
    const tx = await router.completeTask(
      taskId,
      ethers.toUtf8Bytes(result)
    );
    await tx.wait();
  }

  async getOpenTasks(): Promise<any[]> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );

    const count = await router.taskCount();
    const openTasks = [];

    for (let i = 0; i < count; i++) {
      const task = await router.tasks(i);
      if (task[5] === 0) {
        openTasks.push({
          id: i,
          creator: task[0],
          description: task[2],
          reward: task[3],
          deadline: task[4],
        });
      }
    }

    return openTasks;
  }

  /**
   * Subscribe to on-chain contract events via WebSocket with automatic ABI decoding.
   *
   * Uses eth_subscribe("logs") under the hood. On WebSocket disconnect, the
   * WebSocketProvider automatically resubscribes to all active subscriptions
   * so no events are missed after reconnection.
   *
   * @param contractAddress - The contract address to listen to
   * @param contractAbi - The contract ABI (required for event decoding)
   * @param eventName - The name of the event to subscribe to (e.g., "Transfer")
   * @param callback - Called with decoded event data on each log
   * @param indexedFilter - Optional filter for indexed parameters (e.g., { from: "0x..." })
   * @returns Subscription result with sub ID and WebSocket provider for cleanup
   *
   * @example
   * ```typescript
   * const sdk = new OpenAgentsSDK({ ...config, wsUrl: "wss://..." });
   * const { subscriptionId, wsProvider } = await sdk.subscribeToEvents(
   *   "0xContractAddress",
   *   contractAbi,
   *   "Transfer",
   *   (event) => console.log(`${event.name}:`, event.args),
   *   { from: "0xSenderAddress" }
   * );
   * ```
   */
  async subscribeToEvents(
    contractAddress: string,
    contractAbi: ethers.InterfaceAbi,
    eventName: string,
    callback: (event: DecodedEvent) => void,
    indexedFilter?: Record<string, unknown>
  ): Promise<SubscribeResult> {
    if (!this.config.wsUrl) {
      throw new Error(
        "wsUrl is required in AgentConfig to use subscribeToEvents. " +
        "Add wsUrl to your config pointing to a WebSocket RPC endpoint (e.g., wss://mainnet.base.org)."
      );
    }

    // Parse the ABI to get the event definition
    const iface = new ethers.Interface(contractAbi);
    const eventDef = iface.getEvent(eventName);
    if (!eventDef) {
      throw new Error(`Event "${eventName}" not found in provided ABI`);
    }

    const eventTopic = eventDef.topicHash;

    // Build topic filter from indexed parameters
    const topics: (string | null)[] = [eventTopic];

    if (indexedFilter) {
      // Map indexed parameters to their topic positions
      // Indexed params appear in topics[1], topics[2], topics[3]
      for (const input of eventDef.inputs) {
        if (!input.indexed) continue;
        const filterValue = indexedFilter[input.name];
        if (filterValue !== undefined) {
          // Encode the indexed parameter value to match log topics
          const encoded = ethers.AbiCoder.defaultAbiCoder().encode(
            [input.type],
            [filterValue]
          );
          topics.push(encoded);
        } else {
          topics.push(null);
        }
      }
    }

    const filter: EventFilter = {
      address: contractAddress,
      topics,
    };

    // Create WebSocket provider and connect
    const wsConfig: WsProviderConfig = {
      url: this.config.wsUrl,
      reconnectIntervalMs: 3000,
      maxReconnectAttempts: 10,
    };
    const wsProvider = new WebSocketProvider(wsConfig);
    await wsProvider.connect();

    // Subscribe to logs and decode events
    const subscriptionId = await wsProvider.subscribe(
      "logs",
      (rawLog: unknown) => {
        try {
          const log = rawLog as ethers.Log;
          const parsed = iface.parseLog({
            topics: Array.isArray(log.topics) ? [...log.topics] : [log.topics as string],
            data: log.data,
          });

          if (parsed) {
            callback({
              name: parsed.name,
              signature: parsed.signature,
              args: Object.fromEntries(
                parsed.fragment.inputs.map((input, i) => [
                  input.name || `arg${i}`,
                  parsed.args[i],
                ])
              ),
              log,
            });
          }
        } catch (err) {
          // Emit decode errors but don't crash the subscription
          wsProvider.emit("error", new Error(
            `Failed to decode event log: ${err}`
          ));
        }
      },
      [filter]
    );

    return { subscriptionId, wsProvider };
  }
}
