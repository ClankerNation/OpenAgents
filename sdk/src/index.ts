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
import { subscribeToEvents, DecodedEvent, EventFilter, SubscriptionOptions } from "./events";

export { DecodedEvent, EventFilter, SubscriptionOptions };

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
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
   * Subscribe to contract events via WebSocket with automatic reconnection.
   * Converts the HTTP RPC URL to WS automatically if needed.
   *
   * @param contractAddress - Target contract address
   * @param abi - Contract ABI
   * @param eventName - Event name to listen for
   * @param callback - Invoked for each decoded event
   * @param filter - Optional indexed parameter filters
   * @param options - Reconnection configuration
   * @returns Unsubscribe function
   */
  subscribeToEvents(
    contractAddress: string,
    abi: ethers.InterfaceAbi,
    eventName: string,
    callback: (event: DecodedEvent) => void,
    filter: EventFilter = {},
    options: SubscriptionOptions = {},
  ): () => void {
    // Derive WS URL from HTTP RPC URL
    const wsUrl = this.config.rpcUrl
      .replace(/^https?:\/\//, (match) => match === "https://" ? "wss://" : "ws://");

    return subscribeToEvents(
      wsUrl,
      contractAddress,
      abi,
      eventName,
      callback,
      filter,
      options,
    );
  }
}
