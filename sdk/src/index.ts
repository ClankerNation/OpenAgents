// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
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

  /**
   * Simulate a transaction before sending to prevent failed transactions and gas waste.
   * @param tx Transaction request to simulate
   * @returns Simulation result with success status and optional error/revert reason
   */
  async simulateTransaction(tx: ethers.TransactionRequest): Promise<{
    success: boolean;
    gasUsed?: bigint;
    revertReason?: string;
    returnValue?: string;
  }> {
    try {
      const result = await this.provider.call({
        ...tx,
        from: tx.from || this.signer.address,
      });
      
      // Estimate gas for the same transaction
      const gasUsed = await this.provider.estimateGas({
        ...tx,
        from: tx.from || this.signer.address,
      });

      return {
        success: true,
        gasUsed,
        returnValue: result,
      };
    } catch (error: any) {
      return {
        success: false,
        revertReason: error.reason || error.message || "Unknown revert reason",
      };
    }
  }

  /**
   * Send a transaction with pre-flight simulation check.
   * Throws if simulation fails unless skipSimulation is true.
   */
  async safeSendTransaction(
    tx: ethers.TransactionRequest,
    options?: { skipSimulation?: boolean }
  ): Promise<ethers.ContractTransactionResponse> {
    if (!options?.skipSimulation) {
      const sim = await this.simulateTransaction(tx);
      if (!sim.success) {
        throw new Error(`Transaction simulation failed: ${sim.revertReason}`);
      }
    }

    const response = await this.signer.sendTransaction(tx);
    return response as unknown as ethers.ContractTransactionResponse;
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
}
