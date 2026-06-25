import { ethers } from "ethers";

/**
 * Transaction simulation result.
 */
export interface SimulationResult {
  /** Whether the transaction would succeed */
  success: boolean;
  /** Revert reason if failed, null if succeeded */
  reason: string | null;
  /** Estimated gas from simulation (0 if failed) */
  estimatedGas: number;
  /** Raw simulation response */
  rawResult?: unknown;
}

/**
 * Configuration for transaction simulation.
 */
export interface SimulateConfig {
  /** Block number to simulate at (defaults to latest) */
  blockTag?: number | string;
  /** Skip simulation — send transaction anyway */
  skipSimulation?: boolean;
  /** Override from address (defaults to signer.address) */
  from?: string;
}

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

/**
 * Cache key: method + encoded params hashed.
 * Maps to SimulationResult.
 */
interface CacheEntry {
  result: SimulationResult;
  blockNumber: number;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private simulationCache: Map<string, CacheEntry> = new Map();
  private readonly CACHE_TTL_BLOCKS = 10;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = new ethers.JsonRpcProvider(config.rpcUrl);
    this.signer = new ethers.Wallet(config.privateKey, this.provider);
  }

  /**
   * Simulate a transaction before sending to catch reverts early.
   * Uses eth_call and caches results per block to avoid redundant calls.
   * @param txParams Transaction parameters to simulate.
   * @param config Optional simulation config.
   * @returns SimulationResult with success/reason/gas estimate.
   */
  async simulateTransaction(
    txParams: ethers.TransactionRequest,
    config: SimulateConfig = {}
  ): Promise<SimulationResult> {
    const { blockTag, skipSimulation, from } = config;

    if (skipSimulation) {
      return { success: true, reason: null, estimatedGas: 0 };
    }

    // Build cache key from tx params + block
    const cacheKey = `${JSON.stringify(txParams)}:${blockTag ?? "latest"}`;

    // Check cache
    const cached = this.simulationCache.get(cacheKey);
    if (cached) {
      const currentBlock = await this.provider.getBlockNumber();
      if (currentBlock - cached.blockNumber < this.CACHE_TTL_BLOCKS) {
        return cached.result;
      }
      this.simulationCache.delete(cacheKey);
    }

    const simFrom = from || this.signer.address;
    const simTx = { ...txParams, from: simFrom };

    try {
      // Simulate via eth_call
      const gasEstimate = await this.provider.estimateGas(simTx);
      const result: SimulationResult = {
        success: true,
        reason: null,
        estimatedGas: Number(gasEstimate),
      };

      // Cache the result
      const blockNum = await this.provider.getBlockNumber();
      this.simulationCache.set(cacheKey, { result, blockNumber: blockNum });

      return result;
    } catch (err: unknown) {
      // Parse revert reason from error
      let reason = "simulation failed";
      if (err instanceof Error) {
        const msg = err.message;
        // Try to extract revert reason from common error formats
        const match = msg.match(/execution reverted:(.*)/i);
        if (match && match[1]) {
          reason = match[1].trim();
        } else if (msg.includes("reverted")) {
          reason = msg.substring(0, 200);
        } else if (msg.includes("gas")) {
          reason = "out of gas";
        } else {
          reason = msg.substring(0, 200);
        }
      }

      const result: SimulationResult = {
        success: false,
        reason,
        estimatedGas: 0,
      };

      // Still cache failed simulations
      const blockNum = await this.provider.getBlockNumber();
      this.simulationCache.set(cacheKey, { result, blockNumber: blockNum });

      return result;
    }
  }

  /**
   * Send a transaction with automatic simulation check.
   * Reverts pre-send if simulation indicates failure.
   * @param txParams Transaction parameters.
   * @param config Optional simulation config.
   * @returns The signed transaction hash.
   */
  async sendSimulatedTransaction(
    txParams: ethers.TransactionRequest,
    config: SimulateConfig = {}
  ): Promise<string> {
    const simResult = await this.simulateTransaction(txParams, config);

    if (!simResult.success) {
      throw new Error(
        `Transaction simulation failed: ${simResult.reason}${
          simResult.estimatedGas > 0 ? ` (estimated gas: ${simResult.estimatedGas})` : ""
        }`
      );
    }

    // Send the actual transaction
    const tx = await this.signer.sendTransaction(txParams);
    return tx.hash;
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

export { OpenAgentsSDK };
