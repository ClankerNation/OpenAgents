/**
 * @fix-author kejuunuy
 * @fix-date 2026-05-30
 * @fix-issue 196
 * @fix-description Added subscribeToEvents method with ABI decoding, indexed filtering, and WebSocket auto-reconnect
 */

import { ethers } from "ethers";
import {
  EventSubscriptionManager,
  EventSubscriptionConfig,
  AbiEventEntry,
  AbiEventInput,
  DecodedEventLog,
  EventFilter,
  SubscriptionHandle,
  computeEventTopic,
  decodeEventLog,
} from "./events";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
  /** Optional WebSocket RPC URL for event subscriptions */
  wsRpcUrl?: string;
  /** Optional WebSocket provider config for event subscriptions */
  wsConfig?: EventSubscriptionConfig;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private eventManager: EventSubscriptionManager | null = null;

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
   * Subscribe to contract events with ABI decoding and optional indexed parameter filtering.
   *
   * @param contractAddress - The address of the contract to listen to
   * @param abi             - The contract ABI (array of event definitions, or a single event definition)
   * @param eventName       - The name of the event to subscribe to
   * @param callback        - Called with decoded event data on each emission
   * @param filter          - Optional indexed parameter filter
   * @returns SubscriptionHandle with subscriptionId and unsubscribe function
   *
   * @example
   * ```ts
   * const handle = await sdk.subscribeToEvents(
   *   "0x1234...",
   *   [{ type: "event", name: "Transfer", inputs: [
   *     { name: "from", type: "address", indexed: true },
   *     { name: "to", type: "address", indexed: true },
   *     { name: "value", type: "uint256", indexed: false },
   *   ]}],
   *   "Transfer",
   *   (event) => console.log("Transfer:", event.args),
   *   { from: "0xabc..." }
   * );
   *
   * // Later...
   * await handle.unsubscribe();
   * ```
   */
  async subscribeToEvents(
    contractAddress: string,
    abi: AbiEventEntry[] | AbiEventEntry,
    eventName: string,
    callback: (event: DecodedEventLog) => void,
    filter?: EventFilter
  ): Promise<SubscriptionHandle> {
    const manager = this.getEventManager();

    // Find the matching event definition
    const abiArray = Array.isArray(abi) ? abi : [abi];
    const eventDef = abiArray.find(
      (entry) => entry.type === "event" && entry.name === eventName
    );

    if (!eventDef) {
      throw new Error(
        `Event "${eventName}" not found in the provided ABI. ` +
          `Available events: ${abiArray
            .filter((e) => e.type === "event")
            .map((e) => e.name)
            .join(", ") || "(none)"}`
      );
    }

    return manager.subscribeToEvents(
      contractAddress,
      eventDef,
      callback,
      filter
    );
  }

  /**
   * Disconnect all event subscriptions and clean up.
   */
  async disconnectEvents(): Promise<void> {
    if (this.eventManager) {
      await this.eventManager.disconnect();
      this.eventManager = null;
    }
  }

  /**
   * Get or create the EventSubscriptionManager.
   */
  private getEventManager(): EventSubscriptionManager {
    if (!this.eventManager) {
      const eventConfig: EventSubscriptionConfig = {};

      if (this.config.wsConfig) {
        Object.assign(eventConfig, this.config.wsConfig);
      } else if (this.config.wsRpcUrl) {
        eventConfig.wsConfig = { url: this.config.wsRpcUrl };
      } else {
        // Fall back: convert HTTP RPC URL to WS if possible
        const httpUrl = this.config.rpcUrl;
        const wsUrl = httpUrl
          .replace(/^http:\/\//, "ws://")
          .replace(/^https:\/\//, "wss://");
        eventConfig.wsConfig = { url: wsUrl };
      }

      this.eventManager = new EventSubscriptionManager(eventConfig);
    }
    return this.eventManager;
  }
}

// Re-export event types for consumers
export {
  EventSubscriptionManager,
  computeEventTopic,
  decodeEventLog,
  type AbiEventEntry,
  type AbiEventInput,
  type DecodedEventLog,
  type EventFilter,
  type SubscriptionHandle,
  type EventSubscriptionConfig,
} from "./events";
