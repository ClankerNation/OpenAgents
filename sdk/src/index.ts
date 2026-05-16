/*
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * Agent: Metatron (AI — celestial scribe, autonomous coding agent)
 * Platform: Hermes Agent with DeepSeek V4 Pro
 * Environment: Linux x86_64, /home/power, WSL, bash
 * Task: Fix #199 — Add contract deployment helpers to SDK
 * Implementation: deployContract(abi, bytecode, args) with configurable
 *   confirmation blocks, deployment receipt, and constructor arg encoding
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
  transactionHash: string;
  blockNumber: number;
  gasUsed: bigint;
}

export interface DeployOptions {
  /** Number of blocks to wait for confirmation (default: 1) */
  confirmations?: number;
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
   * Deploy a contract to the configured network and return its instance
   * with a full deployment receipt.
   *
   * @param abi - Contract ABI (JSON array or string)
   * @param bytecode - Compiled contract bytecode (hex string, with or without 0x prefix)
   * @param args - Constructor arguments, encoded in order
   * @param options - Optional deployment options (confirmations, etc.)
   * @returns The deployed contract instance (ethers.Contract)
   */
  async deployContract(
    abi: any[] | string,
    bytecode: string,
    args: any[] = [],
    options: DeployOptions = {}
  ) {
    const confirmations = options.confirmations ?? 1;

    // Normalize bytecode to ensure 0x prefix
    const normalizedBytecode = bytecode.startsWith("0x")
      ? bytecode
      : "0x" + bytecode;

    // Create the contract factory with the signer for deployment
    const factory = new ethers.ContractFactory(
      abi,
      normalizedBytecode,
      this.signer
    );

    // Deploy with constructor arguments
    const contract = await factory.deploy(...args);

    // Wait for the specified number of confirmations
    await contract.waitForDeployment();

    // Ensure we have at least the requested confirmations
    if (confirmations > 1) {
      const deployTx = contract.deploymentTransaction();
      if (deployTx) {
        const currentBlock = await this.provider.getBlockNumber();
        const txBlock = deployTx.blockNumber ?? currentBlock;
        const neededConfirmations = confirmations - (currentBlock - txBlock + 1);
        if (neededConfirmations > 0) {
          // Poll until enough blocks pass
          await new Promise<void>((resolve) => {
            const interval = setInterval(async () => {
              const latest = await this.provider.getBlockNumber();
              if (latest - txBlock >= confirmations - 1) {
                clearInterval(interval);
                resolve();
              }
            }, 1000);
          });
        }
      }
    }

    return contract;
  }

  /**
   * Deploy a contract and return a structured deployment receipt.
   *
   * @param abi - Contract ABI (JSON array or string)
   * @param bytecode - Compiled contract bytecode (hex string, with or without 0x prefix)
   * @param args - Constructor arguments, encoded in order
   * @param options - Optional deployment options (confirmations, etc.)
   * @returns DeploymentReceipt with address, transactionHash, blockNumber, gasUsed
   */
  async deployContractWithReceipt(
    abi: any[] | string,
    bytecode: string,
    args: any[] = [],
    options: DeployOptions = {}
  ) {
    const contract = await this.deployContract(abi, bytecode, args, options);
    const deployTx = contract.deploymentTransaction();

    if (!deployTx) {
      throw new Error("Deployment transaction not found — contract may not have been deployed");
    }

    const txReceipt = await deployTx.wait();

    const receipt: DeploymentReceipt = {
      address: await contract.getAddress(),
      transactionHash: deployTx.hash,
      blockNumber: txReceipt?.blockNumber ?? deployTx.blockNumber ?? 0,
      gasUsed: txReceipt?.gasUsed ?? 0n,
    };

    return { contract, receipt };
  }
}
