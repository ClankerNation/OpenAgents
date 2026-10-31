/**
 * Contributor Metadata (required for bounty #196)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 */

import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface DeploymentReceipt {
  address: string;
  transactionHash: string;
  blockNumber: number;
  gasUsed: bigint;
  confirmations: number;
}

export interface EventSubscription {
  contract: ethers.Contract;
  eventName: string;
  callback: (decoded: Record<string, unknown>, raw: ethers.Log) => void;
  filter?: Record<string, unknown>;
  active: boolean;
  unsubscribe: () => void;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private subscriptions: EventSubscription[] = [];
  private reconnecting = false;

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

  async deployContract(
    abi: any[],
    bytecode: string,
    args: unknown[] = [],
    confirmations: number = 1
  ): Promise<DeploymentReceipt> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);
    const receipt = await contract.deploymentTransaction()?.wait(confirmations);

    if (!receipt) {
      throw new Error("Deployment transaction receipt not found");
    }

    return {
      address: await contract.getAddress(),
      transactionHash: receipt.hash,
      blockNumber: receipt.blockNumber,
      gasUsed: receipt.gasUsed,
      confirmations,
    };
  }

  /**
   * Subscribe to on-chain events from a contract.
   * @param contractAddress - The contract address to listen to
   * @param abi - The contract ABI (for event decoding)
   * @param eventName - The event name to listen for
   * @param callback - Called when an event is received with decoded parameters
   * @param filter - Optional filter by indexed parameters
   * @returns EventSubscription with unsubscribe method
   */
  subscribeToEvents(
    contractAddress: string,
    abi: any[],
    eventName: string,
    callback: (decoded: Record<string, unknown>, raw: ethers.Log) => void,
    filter?: Record<string, unknown>
  ): EventSubscription {
    const contract = new ethers.Contract(contractAddress, abi, this.provider);

    const subscription: EventSubscription = {
      contract,
      eventName,
      callback,
      filter,
      active: true,
      unsubscribe: () => {
        subscription.active = false;
        contract.removeAllListeners(eventName);
      },
    };

    const listener = (log: ethers.Log) => {
      if (!subscription.active) return;

      try {
        const parsed = contract.interface.parseLog({
          topics: log.topics as string[],
          data: log.data,
        });

        if (!parsed || parsed.name !== eventName) return;

        // Decode parameters
        const decoded: Record<string, unknown> = {};
        parsed.args.forEach((arg, idx) => {
          const name = parsed.fragment.inputs[idx]?.name || `arg${idx}`;
          decoded[name] = arg;
        });

        // Apply indexed parameter filter
        if (filter) {
          for (const [key, value] of Object.entries(filter)) {
            if (decoded[key] !== value) return;
          }
        }

        callback(decoded, log);
      } catch (err) {
        console.error(`Error decoding event ${eventName}:`, err);
      }
    };

    contract.on(eventName, listener);

    // Store subscription for reconnect handling
    this.subscriptions.push(subscription);

    return subscription;
  }

  /**
   * Unsubscribe from all active event subscriptions.
   */
  unsubscribeAll(): void {
    for (const sub of this.subscriptions) {
      sub.unsubscribe();
    }
    this.subscriptions = [];
  }

  /**
   * Get the number of active subscriptions.
   */
  getActiveSubscriptionCount(): number {
    return this.subscriptions.filter((s) => s.active).length;
  }
}
