import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export type EventCallback = (log: ethers.Log, decoded: ethers.LogDescription | null) => void;

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private eventSubscriptions: Map<string, { contract: ethers.Contract; listener: any }> = new Map();

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

  subscribeToEvents(
    contract: ethers.Contract,
    eventName: string,
    callback: EventCallback,
    filter?: Record<string, any>,
  ): string {
    const subId = `${contract.target}-${eventName}-${Date.now()}`;
    const listener = (...args: any[]) => {
      const log = args[args.length - 1] as ethers.Log;
      let decoded: ethers.LogDescription | null = null;
      try {
        const iface = contract.interface;
        decoded = iface.parseLog({ topics: [...log.topics], data: log.data });
      } catch {
        decoded = null;
      }
      callback(log, decoded);
    };
    const filterArgs: any[] = [];
    if (filter) {
      filterArgs.push(filter);
    }
    contract.on(eventName, ...filterArgs, listener);
    this.eventSubscriptions.set(subId, { contract, listener });
    return subId;
  }

  unsubscribeFromEvents(subId: string): boolean {
    const sub = this.eventSubscriptions.get(subId);
    if (!sub) return false;
    sub.contract.off(sub.listener);
    this.eventSubscriptions.delete(subId);
    return true;
  }

  unsubscribeAll(): void {
    for (const [, sub] of this.eventSubscriptions) {
      sub.contract.off(sub.listener);
    }
    this.eventSubscriptions.clear();
  }
}
