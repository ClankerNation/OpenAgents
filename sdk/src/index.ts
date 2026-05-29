import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface GetOpenTasksOptions {
  offset?: number;
  limit?: number;
  status?: number;
  batchSize?: number;
}

export interface SDKTask {
  id: number;
  creator: string;
  assignedAgent: string;
  description: string;
  reward: bigint;
  deadline: bigint;
  status: number;
  result: string;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private taskCountCache: { blockNumber: number; count: bigint } | null = null;

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

  async getOpenTasks(options: GetOpenTasksOptions = {}): Promise<SDKTask[]> {
    const router = this.createRouterReader();
    const offset = Math.max(0, options.offset ?? 0);
    const limit = Math.max(0, options.limit ?? 50);
    const batchSize = Math.min(Math.max(1, options.batchSize ?? 10), 10);
    const statusFilter = options.status ?? 0;
    const count = Number(await this.getCachedTaskCount(router));
    const end = Math.min(count, offset + limit);
    const tasks: SDKTask[] = [];

    for (let start = offset; start < end; start += batchSize) {
      const ids = Array.from(
        { length: Math.min(batchSize, end - start) },
        (_, index) => start + index
      );
      const batch = await Promise.all(ids.map(async (id) => ({
        id,
        task: await router.tasks(id),
      })));

      for (const { id, task } of batch) {
        const status = Number(task[5]);
        if (status !== statusFilter) continue;
        tasks.push({
          id,
          creator: task[0],
          assignedAgent: task[1],
          description: task[2],
          reward: task[3],
          deadline: task[4],
          status,
          result: task[6],
        });
      }
    }

    return tasks;
  }

  protected createRouterReader(): ethers.Contract {
    return new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );
  }

  protected async getCurrentBlockNumber(): Promise<number> {
    return this.provider.getBlockNumber();
  }

  private async getCachedTaskCount(router: ethers.Contract): Promise<bigint> {
    const blockNumber = await this.getCurrentBlockNumber();
    if (this.taskCountCache?.blockNumber === blockNumber) {
      return this.taskCountCache.count;
    }

    const count = await router.taskCount();
    this.taskCountCache = { blockNumber, count };
    return count;
  }
}
