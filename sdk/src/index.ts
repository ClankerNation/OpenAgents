// @fix-author: Metatron | Platform: Hermes Agent | OS: linux | Arch: x64
// @fix-author Home: /home/power | Workdir: /home/power/projects/OpenAgents | Shell: /bin/bash
// @fix-task: GitHub Issue #196 — Add event subscription and decoding to OpenAgentsSDK
// @fix-context: CRON JOB with these instructions in order:
//   1. Check status of ALL open PRs by invisiblemonsters on ClankerNation/OpenAgents
//   2. Report any status changes (merged, review requested, changes requested)
//   3. IF A PR NEEDS CHANGES: Read review comments, fix code, push fix
//   4. IF ALL PRs CLEAN: Read /home/power/.hermes/scripts/bounty_board.md, work on highest priority unclaimed bounty
//   5. Implement fix with tests, add traceability header, update CONTRIBUTORS.json, submit PR
//   Bounty rules: Never work on issue with open PR from invisiblemonsters. Prefer Solidity.
//   The user instruction: "You are Metatron's autonomous bounty-hunting loop. You wake up every 30 minutes to generate income."
// @fix-summary: Added subscribeToEvents() method to OpenAgentsSDK with ABI decoding, indexed filtering, and auto-reconnect.

import { ethers } from "ethers";
import {
  EventSubscriber,
  EventFilter,
  EventCallback,
  EventSubscription,
} from "./events/subscription";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
  /** Optional WebSocket URL for real-time event subscriptions */
  wsUrl?: string;
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
   * Subscribe to real-time contract events via WebSocket.
   *
   * Creates a persistent WebSocket connection that listens for on-chain
   * events from the specified contract. Events are decoded using the
   * provided ABI and delivered to the callback with named arguments.
   * Supports filtering by indexed parameters and auto-reconnects on
   * WebSocket drops.
   *
   * @param contractAddress - The deployed contract address to listen to
   * @param contractAbi - The contract ABI (must include the event definition)
   * @param eventName - The Solidity event name (e.g., "Transfer")
   * @param filter - Optional indexed parameter filters (e.g., { from: "0x..." })
   * @param callback - Called for each matching event with decoded args and raw log
   * @returns EventSubscription with unsubscribe() method to stop listening
   *
   * @example
   * const sub = await sdk.subscribeToEvents(
   *   routerAddress,
   *   taskRouterAbi,
   *   "TaskCreated",
   *   {},
   *   (event) => console.log("New task:", event.args.taskId)
   * );
   * // Later: sub.unsubscribe();
   */
  async subscribeToEvents(
    contractAddress: string,
    contractAbi: ethers.InterfaceAbi,
    eventName: string,
    filter: EventFilter,
    callback: EventCallback
  ): Promise<EventSubscription> {
    const wsUrl =
      this.config.wsUrl ||
      this.config.rpcUrl.replace(/^https?:/, "ws:").replace(/\/$/, "") + "/ws";

    if (!this.eventSubscriber) {
      this.eventSubscriber = new EventSubscriber(wsUrl, contractAbi);
    }

    return this.eventSubscriber.subscribe(
      contractAddress,
      eventName,
      filter,
      callback
    );
  }

  /**
   * Clean up the event subscriber and all active subscriptions.
   */
  destroyEventSubscriber(): void {
    if (this.eventSubscriber) {
      this.eventSubscriber.destroy();
      this.eventSubscriber = null;
    }
  }
}
