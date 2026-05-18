import { ethers } from "ethers";
import { EventSubscriber, EventSubscriberConfig, EventFilter, DecodedEvent, EventSubscription } from "./events";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  wsUrl?: string;
  registryAddress: string;
  routerAddress: string;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private eventSubscriber: EventSubscriber | null = null;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = new ethers.JsonRpcProvider(config.rpcUrl);
    this.signer = new ethers.Wallet(config.privateKey, this.provider);

    if (config.wsUrl) {
      this.eventSubscriber = new EventSubscriber({
        wsUrl: config.wsUrl,
        reconnectIntervalMs: 3000,
        maxReconnectAttempts: 10,
      });
    }
  }

  // --- Existing Methods ---

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

  // --- Event Subscription Methods ---

  /**
   * Connect to the WebSocket provider for real-time event subscriptions.
   * Must be called before subscribeToEvents, subscribeLogs, or onEvent.
   */
  async connectEvents(): Promise<void> {
    if (!this.eventSubscriber) {
      if (!this.config.wsUrl) {
        throw new Error("wsUrl must be provided in AgentConfig to use event subscriptions");
      }
      this.eventSubscriber = new EventSubscriber({
        wsUrl: this.config.wsUrl,
        reconnectIntervalMs: 3000,
        maxReconnectAttempts: 10,
      });
    }
    await this.eventSubscriber.connect();
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
    callback: (event: DecodedEvent) => void,
    filter?: EventFilter
  ): Promise<EventSubscription> {
    if (!this.eventSubscriber) {
      throw new Error("EventSubscriber not initialized — call connectEvents() first");
    }
    return this.eventSubscriber.subscribeToEvents(contractAddress, abi, eventName, callback, filter);
  }

  /**
   * Subscribe to all events from a contract address (wildcard listener).
   *
   * @param contractAddress - Address to monitor
   * @param abi - ABI fragments for decoding all events
   * @param callback - Called for each decoded event
   * @returns Subscription handle
   */
  async subscribeLogs(
    contractAddress: string,
    abi: ethers.Fragment | ethers.Fragment[] | string | string[],
    callback: (event: DecodedEvent) => void
  ): Promise<EventSubscription> {
    if (!this.eventSubscriber) {
      throw new Error("EventSubscriber not initialized — call connectEvents() first");
    }
    return this.eventSubscriber.subscribeLogs(contractAddress, abi, callback);
  }

  /**
   * Shorthand for subscribeToEvents — register an onEvent handler.
   *
   * @param contractAddress - On-chain contract address to monitor
   * @param abi - Contract ABI fragments for event decoding
   * @param eventName - The specific event name to subscribe to
   * @param callback - Called with each decoded event
   * @param filter - Optional filter for indexed parameters
   * @returns Subscription handle
   */
  async onEvent(
    contractAddress: string,
    abi: ethers.Fragment | ethers.Fragment[] | string | string[],
    eventName: string,
    callback: (event: DecodedEvent) => void,
    filter?: EventFilter
  ): Promise<EventSubscription> {
    return this.subscribeToEvents(contractAddress, abi, eventName, callback, filter);
  }

  /**
   * Unsubscribe from an active event subscription.
   */
  unsubscribeEvents(subscription: EventSubscription): void {
    this.eventSubscriber?.unsubscribe(subscription);
  }

  /**
   * Disconnect from the WebSocket event provider.
   */
  disconnectEvents(): void {
    this.eventSubscriber?.disconnect();
  }
}

export { EventSubscriber, EventSubscriberConfig, EventFilter, DecodedEvent, EventSubscription };
