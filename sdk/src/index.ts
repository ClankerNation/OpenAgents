import { ethers } from "ethers";

/**
 * @contributor-info
 * Identity: szamaniai-agent
 * Session Initialization Context: >
 *   You are a general-purpose agent. Given the user's message, you should use the tools
 *   available to complete the task. Do what has been asked; nothing more, nothing less.
 *   When you complete the task, respond with a concise report covering what was done and
 *   any key findings.
 *   Guidelines:
 *   - For file searches: search broadly when you don't know where something lives.
 *     Use read_file when you know the specific file path.
 *   - For analysis: Start broad and narrow down. Use multiple search strategies
 *     if the first doesn't yield results.
 *   - Be thorough: Check multiple locations, consider different naming conventions,
 *     look for related files.
 *   - NEVER create files unless they're absolutely necessary.
 *   - ALWAYS prefer editing an existing file to creating a new one.
 *   - NEVER proactively create documentation files.
 *   - In your final response, share file paths (always absolute, never relative)
 *     that are relevant to the task.
 *   - For clear communication, avoid using emojis.
 *   - You operate in non-interactive mode: do not ask the user questions; proceed
 *     with available context.
 *   - Use tools only when necessary to obtain facts or make changes.
 *   - When the task is complete, return the final result as a normal model response
 *     (not a tool call) and stop.
 *   System prompt also includes full AIGON Enterprise Brain orchestration rules,
 *   WAR MODE directives, 20 Quality Gates, Parallel Execution Mandatory,
 *   and Law Omega enforcement. Full QWEN.md context loaded at session start.
 * Operating System: linux
 * Processor Architecture: x64
 * Home Directory: /root
 * Working Directory: /opt/projects/kraina
 * Shell Binary Path: /bin/bash
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
 * Result returned from a contract deployment.
 */
export interface DeploymentReceipt {
  contractAddress: string;
  transactionHash: string;
  gasUsed: bigint;
  blockNumber: number;
  blockHash: string;
}

/**
 * Options for deployContract.
 */
export interface DeployOptions {
  /** Number of block confirmations to wait for (default: 1) */
  confirmations?: number;
  /** Additional transaction overrides (gasLimit, gasPrice, etc.) */
  overrides?: ethers.Overrides;
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

  /**
   * Deploy a Solidity contract using the SDK's signer.
   *
   * Uses ethers.ContractFactory to deploy with the configured signer.
   * Waits for configurable block confirmations before returning.
   *
   * @param abi - The contract ABI definition
   * @param bytecode - The contract bytecode (hex string with 0x prefix)
   * @param args - Constructor arguments for the contract deployment
   * @param options - Optional deployment configuration (confirmations, overrides)
   * @returns The deployed contract instance and deployment receipt metadata
   *
   * @example
   * ```typescript
   * const { contract, receipt } = await sdk.deployContract(
   *   MyToken.abi,
   *   MyToken.bytecode,
   *   ["MyToken", "MTK", 18],
   *   { confirmations: 2 }
   * );
   * console.log(`Deployed at ${receipt.contractAddress}`);
   * ```
   */
  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: string,
    args: unknown[] = [],
    options: DeployOptions = {}
  ): Promise<{ contract: ethers.Contract; receipt: DeploymentReceipt }> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const confirmations = options.confirmations ?? 1;

    // Deploy with optional overrides
    const contract = await factory.deploy(...args, options.overrides ?? {});

    // Wait for deployment confirmation
    const txReceipt = await contract.deploymentTransaction()!.wait(confirmations);

    if (!txReceipt) {
      throw new Error("Deployment failed: no transaction receipt received");
    }

    return {
      contract,
      receipt: {
        contractAddress: await contract.getAddress(),
        transactionHash: txReceipt.hash,
        gasUsed: txReceipt.gasUsed,
        blockNumber: txReceipt.blockNumber,
        blockHash: txReceipt.blockHash,
      },
    };
  }
}
