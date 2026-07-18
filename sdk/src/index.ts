// @contributor-info
// Name: freebuff (via hanu-14)
// Date: 2026-07-18
// Runtime: win32 | AMD64 | C:\Projects\OSS\OpenAgents | bash
// Task: Add deployContract helper to SDK (Issue #199)

import { ethers } from "ethers";

/**
 * Result of a successful contract deployment.
 */
export interface DeployResult {
  /** Address the contract was deployed to. */
  address: string;
  /** Transaction hash of the deployment. */
  txHash: string;
  /** Gas consumed by the deployment. */
  gasUsed: bigint;
  /** The deployed contract instance (ethers Contract). */
  contract: ethers.Contract;
}

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
   * Deploy a smart contract using its ABI, bytecode, and constructor arguments.
   *
   * @param abi       Contract ABI (JSON array or ethers Interface).
   * @param bytecode  Deployed bytecode ("0x"-prefixed hex string).
   * @param args      Constructor arguments as an array.
   * @param confirmations  Number of block confirmations to wait for (default: 1).
   * @returns DeployResult containing address, tx hash, gas used, and contract instance.
   *
   * @example
   * ```ts
   * const result = await sdk.deployContract(
   *   ["constructor(uint256 _initial)", "function get() view returns (uint256)"],
   *   "0x608060...",
   *   [100n]
   * );
   * console.log(`Deployed at ${result.address}`);
   * ```
   */
  async deployContract(
    abi: ethers.Interface | Array<ethers.Fragment | string | object>,
    bytecode: string,
    args: unknown[] = [],
    confirmations: number = 1
  ): Promise<DeployResult> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const deployed = await factory.deploy(...args);
    const receipt = await deployed.waitForDeployment();
    const address = await deployed.getAddress();

    // Retrieve the deployment receipt for metadata
    const txHash = deployed.deploymentTransaction()?.hash ?? "";
    let gasUsed = 0n;
    if (txHash) {
      const txReceipt = await this.provider.getTransactionReceipt(txHash);
      if (txReceipt) {
        gasUsed = txReceipt.gasUsed;
      }
    }

    // Wait for additional confirmations if requested
    if (confirmations > 1) {
      await deployed.deploymentTransaction()?.wait(confirmations);
    }

    return {
      address,
      txHash,
      gasUsed,
      contract: deployed,
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
