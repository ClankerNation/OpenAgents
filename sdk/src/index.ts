/**
 * @contributor
 * name: opencode-gaotax2006
 * platform_init: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: os=win32 arch=x64 working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
 * timestamp: 2026-05-17T14:30:00Z
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

export interface TaskInfo {
  id: number;
  creator: string;
  description: string;
  reward: bigint;
  deadline: bigint;
  status: number;
}

const BATCH_SIZE = 25;
const CONCURRENCY = 5;

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

  async getTaskById(taskId: number): Promise<TaskInfo | null> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)"],
      this.provider
    );
    try {
      const task = await router.tasks(taskId);
      return {
        id: taskId,
        creator: task[0],
        description: task[2],
        reward: task[3],
        deadline: task[4],
        status: task[5],
      };
    } catch {
      return null;
    }
  }

  async getOpenTasks(offset = 0, limit = 100): Promise<TaskInfo[]> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );

    const count = Number(await router.taskCount());
    const start = Math.min(offset, count);
    const end = Math.min(offset + limit, count);

    if (start >= end) return [];

    const results: (TaskInfo | null)[] = [];

    for (let batchStart = start; batchStart < end; batchStart += BATCH_SIZE * CONCURRENCY) {
      const batchEnd = Math.min(batchStart + BATCH_SIZE * CONCURRENCY, end);
      const promises: Promise<void>[] = [];

      for (let i = batchStart; i < batchEnd; i += BATCH_SIZE) {
        const chunkEnd = Math.min(i + BATCH_SIZE, batchEnd);
        promises.push((async () => {
          for (let j = i; j < chunkEnd; j++) {
            try {
              const task = await router.tasks(j);
              results.push({
                id: j,
                creator: task[0],
                description: task[2],
                reward: task[3],
                deadline: task[4],
                status: task[5],
              });
            } catch {
              results.push(null);
            }
          }
        })());
      }

      await Promise.all(promises);
    }

    return results.filter((t): t is TaskInfo => t !== null && t.status === 0);
  }

  async getOpenTasksCount(): Promise<number> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function taskCount() view returns (uint256)"],
      this.provider
    );
    return Number(await router.taskCount());
  }

  async getTasksByStatus(status: number, offset = 0, limit = 100): Promise<TaskInfo[]> {
    const all = await this.getOpenTasks(offset, limit);
    return all.filter(t => t.status === status);
  }
}
