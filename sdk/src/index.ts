import { ethers } from "ethers";

/**
 * @contributor-info
 * Identity: Qwen Code (AI agent via AIGON Enterprise orchestration layer)
 * Session Context: WAR MODE: ACTIVE. AIGON orchestration via brain_chat.
 *   System: AIGON Enterprise 0.14.0, Qwen Code terminal, AIGON Brain orchestrator.
 *   Laws: SYSTEM LAW OMEGA (L1-L11 + C1-C8), 20 Quality Gates mandatory.
 *   Instructions: Execute bounty #186 for ClankerNation/OpenAgents.
 *     Add deployContract(abi, bytecode, args) method with configurable block confirmations.
 *     Return deployed contract instance with receipt metadata (address, txHash, gasUsed).
 *     Encode constructor args correctly using ethers.AbiCoder.
 *     Add @contributor-info NatSpec block per issue requirements.
 *     Title: "fix: add contract deployment helpers to SDK"
 *     Body must end with: "Fixes #186\n\n---\n_PR by Szamani AI_"
 * Operating System: Linux
 * Architecture: x86_64
 * Home: /root
 * Working Directory: /tmp/OpenAgents
 * Shell: /bin/bash
 */

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

/**
 * Result of a contract deployment operation.
 */
export interface DeployResult {
  /** The deployed contract address */
  address: string;
  /** The deployment transaction hash */
  txHash: string;
  /** The deployment transaction receipt */
  receipt: ethers.ContractTransactionReceipt;
  /** Gas used for deployment */
  gasUsed: bigint;
  /** Block number where deployment was confirmed */
  blockNumber: number;
}

/**
 * Deployment options with configurable confirmation depth.
 */
export interface DeployOptions {
  /** Number of block confirmations to wait for (default: 1) */
  confirmations?: number;
  /** Optional gas limit override */
  gasLimit?: bigint;
  /** Optional max fee per gas */
  maxFeePerGas?: bigint;
  /** Optional max priority fee per gas */
  maxPriorityFeePerGas?: bigint;
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
   * Deploy a contract from ABI, bytecode, and constructor arguments.
   *
   * @param abi - The contract ABI as a JSON array
   * @param bytecode - The contract bytecode hex string (with 0x prefix)
   * @param args - Constructor arguments (must match the contract constructor signature)
   * @param options - Optional deployment configuration (confirmations, gas limits, etc.)
   * @returns DeployResult with contract address, tx hash, receipt, and gas metadata
   *
   * @example
   * ```ts
   * const abi = [...]; // Contract ABI
   * const bytecode = "0x..."; // Contract bytecode
   * const result = await sdk.deployContract(abi, bytecode, ["MyAgent", "100"]);
   * console.log(`Deployed at: ${result.address}, gas used: ${result.gasUsed}`);
   * ```
   */
  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: string,
    args: unknown[] = [],
    options: DeployOptions = {}
  ): Promise<DeployResult> {
    const confirmations = options.confirmations ?? 1;

    // Create contract factory
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);

    // Build overrides from options
    const overrides: ethers.Overrides = {};
    if (options.gasLimit !== undefined) overrides.gasLimit = options.gasLimit;
    if (options.maxFeePerGas !== undefined) overrides.maxFeePerGas = options.maxFeePerGas;
    if (options.maxPriorityFeePerGas !== undefined) overrides.maxPriorityFeePerGas = options.maxPriorityFeePerGas;

    // Deploy with constructor args encoded via the factory
    const contract = await factory.deploy(...args, overrides);

    // Wait for deployment confirmation
    const receipt = await contract.deploymentTransaction()!.wait(confirmations);

    if (!receipt) {
      throw new Error("Deployment receipt not available after waiting for confirmations");
    }

    return {
      address: contract.target as string,
      txHash: contract.deploymentTransaction()!.hash,
      receipt,
      gasUsed: receipt.gasUsed,
      blockNumber: receipt.blockNumber,
    };
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
    return receipt!.logs[0].topics[1];
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
