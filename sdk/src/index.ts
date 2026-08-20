/**
 * @contributor-info rafaio1
 * @timestamp 2026-08-20T00:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
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

export interface DeploymentReceipt {
  address: string;
  txHash: string;
  gasUsed: bigint;
  blockNumber: number;
  confirmations: number;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private _taskCountCache: { value: number; blockNumber: number } | null = null;

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

  /**
   * Deploy a contract and wait for confirmation.
   * @param abi Contract ABI (JSON array or human-readable)
   * @param bytecode Contract bytecode (hex string with 0x prefix)
   * @param args Constructor arguments
   * @param confirmations Number of block confirmations to wait (default: 1)
   * @returns DeploymentReceipt with address, tx hash, gas used, etc.
   */
  async deployContract(
    abi: any[],
    bytecode: string,
    args: unknown[] = [],
    confirmations: number = 1
  ): Promise<DeploymentReceipt> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);
    
    // Wait for deployment transaction to be mined
    const receipt = await contract.deploymentTransaction()?.wait(confirmations);
    
    if (!receipt || !contract.target) {
      throw new Error("Deployment failed: no receipt or contract address");
    }

    return {
      address: contract.target as string,
      txHash: receipt.hash,
      gasUsed: receipt.gasUsed,
      blockNumber: receipt.blockNumber,
      confirmations: receipt.confirmations,
    };
  }

  async getOpenTasks(options?: {
    offset?: number;
    limit?: number;
    status?: number;
  }): Promise<any[]> {
    const offset = options?.offset ?? 0;
    const limit = options?.limit ?? 50;
    const statusFilter = options?.status ?? 0; // Default to Open (0)

    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );

    // Cache task count per block
    const currentBlock = await this.provider.getBlockNumber();
    let count: bigint;

    if (this._taskCountCache && this._taskCountCache.blockNumber === currentBlock) {
      count = BigInt(this._taskCountCache.value);
    } else {
      count = await router.taskCount();
      this._taskCountCache = { value: Number(count), blockNumber: currentBlock };
    }

    const end = Math.min(offset + limit, Number(count));
    if (offset >= Number(count)) return [];

    const openTasks = [];
    const batchSize = 10;

    for (let i = offset; i < end; i += batchSize) {
      const batchEnd = Math.min(i + batchSize, end);
      const promises = [];
      for (let j = i; j < batchEnd; j++) {
        promises.push(router.tasks(j).then((t: any) => ({ id: j, data: t })));
      }

      const results = await Promise.all(promises);
      for (const result of results) {
        const task = result.data;
        if (task[5] === statusFilter) {
          openTasks.push({
            id: result.id,
            creator: task[0],
            description: task[2],
            reward: task[3],
            deadline: task[4],
            status: task[5],
          });
        }
      }
    }

    return openTasks;
  }
}
