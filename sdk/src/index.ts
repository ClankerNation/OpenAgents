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


export interface GasEstimate {
  gasLimit: bigint;
  maxFeePerGas?: bigint;
  maxPriorityFeePerGas?: bigint;
  gasPrice?: bigint;
}

const GAS_MARGIN_MULTIPLIER = 1.2; // 20% safety margin

async function estimateGasWithMargin(
  provider: ethers.JsonRpcProvider,
  tx: ethers.TransactionRequest,
  manualGasLimit?: bigint
): Promise<GasEstimate> {
  if (manualGasLimit) {
    return { gasLimit: manualGasLimit };
  }

  const estimated = await provider.estimateGas(tx);
  const withMargin = BigInt(Math.ceil(Number(estimated) * GAS_MARGIN_MULTIPLIER));

  // Cap at block gas limit
  const block = await provider.getBlock("latest");
  const capped = block?.gasLimit ? (withMargin < block.gasLimit ? withMargin : block.gasLimit) : withMargin;

  // EIP-1559 support
  try {
    const feeData = await provider.getFeeData();
    if (feeData.maxFeePerGas && feeData.maxPriorityFeePerGas) {
      return {
        gasLimit: capped,
        maxFeePerGas: feeData.maxFeePerGas,
        maxPriorityFeePerGas: feeData.maxPriorityFeePerGas,
      };
    }
  } catch {}

  // Legacy fallback
  const feeData = await provider.getFeeData();
  return {
    gasLimit: capped,
    gasPrice: feeData.gasPrice ?? undefined,
  };
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
    const txData = await registry.registerAgent.populateTransaction(
      this.config.name,
      this.config.endpoint,
      { value: fee }
    );
    const gas = await estimateGasWithMargin(this.provider, { ...txData, value: fee });
    const tx = await registry.registerAgent(
      this.config.name,
      this.config.endpoint,
      { value: fee, ...gas }
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
    const txData = await router.assignTask.populateTransaction(taskId, agentId);
    const gas = await estimateGasWithMargin(this.provider, txData);
    const tx = await router.assignTask(taskId, agentId, gas);
    await tx.wait();
  }

  async submitResult(taskId: number, result: string): Promise<void> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function completeTask(uint256,bytes)"],
      this.signer
    );
    const txData = await router.completeTask.populateTransaction(
      taskId,
      ethers.toUtf8Bytes(result)
    );
    const gas = await estimateGasWithMargin(this.provider, txData);
    const tx = await router.completeTask(
      taskId,
      ethers.toUtf8Bytes(result),
      gas
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
