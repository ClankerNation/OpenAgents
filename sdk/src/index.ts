/**
 * @fix-author rafaio1
 * @date 2026-08-20T13:25:00Z
 * @runtime os=linux, arch=x64, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
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

  // Cache for task count per block to avoid redundant RPC calls
  private _taskCountCache: { block: number; count: number } | null = null;

  /**
   * Get open tasks with pagination, concurrency, and status filtering.
   * @param options.offset Start index (default 0)
   * @param options.limit Max tasks to fetch (default 50)
   * @param options.statusFilter Optional status code filter (0=Open, 1=Assigned, etc.)
   * @param options.batchSize Concurrent requests per batch (default 10)
   */
  async getOpenTasks(options: {
    offset?: number;
    limit?: number;
    statusFilter?: number;
    batchSize?: number;
  } = {}): Promise<any[]> {
    const offset = options.offset ?? 0;
    const limit = options.limit ?? 50;
    const statusFilter = options.statusFilter ?? 0; // Default to Open tasks
    const batchSize = options.batchSize ?? 10;

    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );

    // Get task count with per-block caching
    const currentBlock = await this.provider.getBlockNumber();
    let totalCount: number;
    if (this._taskCountCache && this._taskCountCache.block === currentBlock) {
      totalCount = this._taskCountCache.count;
    } else {
      totalCount = Number(await router.taskCount());
      this._taskCountCache = { block: currentBlock, count: totalCount };
    }

    // Calculate actual range
    const startIdx = Math.min(offset, totalCount);
    const endIdx = Math.min(offset + limit, totalCount);
    const indices: number[] = [];
    for (let i = startIdx; i < endIdx; i++) {
      indices.push(i);
    }

    if (indices.length === 0) return [];

    // Fetch tasks in concurrent batches
    const results: any[] = [];
    for (let b = 0; b < indices.length; b += batchSize) {
      const batch = indices.slice(b, b + batchSize);
      const batchResults = await Promise.all(
        batch.map(async (idx) => {
          try {
            const task = await router.tasks(idx);
            return { idx, task };
          } catch {
            return { idx, task: null };
          }
        })
      );

      for (const { idx, task } of batchResults) {
        if (!task) continue;
        // Apply status filter
        if (task[5] === statusFilter) {
          results.push({
            id: idx,
            creator: task[0],
            description: task[2],
            reward: task[3],
            deadline: task[4],
            status: task[5],
          });
        }
      }
    }

    return results;
  }
}
