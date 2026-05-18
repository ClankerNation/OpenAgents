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
  /** Address of the deployed contract */
  address: string;
  /** Deployment transaction hash */
  transactionHash: string;
  /** Block number where the contract was deployed */
  blockNumber: number;
  /** Gas used for the deployment transaction */
  gasUsed: bigint;
}

export interface DeployOptions {
  /** Number of blocks to wait for confirmation (default: 1) */
  confirmations?: number;
  /** Gas limit override for deployment (optional) */
  gasLimit?: bigint;
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
   * Deploy a contract to the configured network.
   *
   * Uses ethers.ContractFactory with the SDK's signer to deploy a contract
   * with the given ABI, bytecode, and constructor arguments. Automatically
   * normalizes the bytecode (adds 0x prefix if missing) and waits for
   * deployment confirmation.
   *
   * @param abi - Contract ABI (JSON array or string)
   * @param bytecode - Compiled contract bytecode (hex, with or without 0x prefix)
   * @param args - Constructor arguments in order
   * @param options - Optional deployment options (confirmations, gas limit)
   * @returns Deployed ethers.Contract instance
   *
   * @example
   * ```ts
   * const sdk = new OpenAgentsSDK(config);
   * const contract = await sdk.deployContract(
   *   MyContract.abi,
   *   MyContract.bytecode,
   *   [arg1, arg2],
   *   { confirmations: 3 }
   * );
   * console.log(await contract.getAddress());
   * ```
   */
  async deployContract(
    abi: any[] | string,
    bytecode: string,
    args: any[] = [],
    options: DeployOptions = {}
  ): Promise<ethers.BaseContract> {
    const confirmations = options.confirmations ?? 1;

    if (confirmations < 1) {
      throw new Error("confirmations must be >= 1");
    }

    // Normalize bytecode
    const normalizedBytecode = bytecode.startsWith("0x")
      ? bytecode
      : "0x" + bytecode;

    // Validate bytecode looks like valid hex
    if (!/^0x[0-9a-fA-F]+$/.test(normalizedBytecode)) {
      throw new Error("Invalid bytecode: must be hex string");
    }

    const overrides: any = {};
    if (options.gasLimit !== undefined) {
      overrides.gasLimit = options.gasLimit;
    }

    const factory = new ethers.ContractFactory(
      abi,
      normalizedBytecode,
      this.signer
    );

    // Deploy with constructor args
    const contract = await factory.deploy(...args, overrides);

    // Wait for deployment to be mined
    await contract.waitForDeployment();

    // Wait for additional confirmations if requested
    if (confirmations > 1) {
      const deployTx = contract.deploymentTransaction();
      if (deployTx) {
        const txBlock = deployTx.blockNumber;
        if (txBlock) {
          await this._waitForConfirmations(txBlock, confirmations);
        }
      }
    }

    return contract;
  }

  /**
   * Deploy a contract and return a structured receipt with deployment metadata.
   *
   * This wraps deployContract and extracts address, transaction hash,
   * block number, and gas used into a DeploymentReceipt object.
   *
   * @param abi - Contract ABI
   * @param bytecode - Compiled contract bytecode
   * @param args - Constructor arguments
   * @param options - Deployment options
   * @returns DeploymentReceipt with deployment metadata
   */
  async deployContractWithReceipt(
    abi: any[] | string,
    bytecode: string,
    args: any[] = [],
    options: DeployOptions = {}
  ): Promise<DeploymentReceipt> {
    const contract = await this.deployContract(abi, bytecode, args, options);

    const deployTx = contract.deploymentTransaction();
    if (!deployTx) {
      throw new Error("Deployment transaction not found after deployment");
    }

    const txReceipt = await deployTx.wait();
    if (!txReceipt) {
      throw new Error("Failed to get deployment transaction receipt");
    }

    return {
      address: await contract.getAddress(),
      transactionHash: deployTx.hash,
      blockNumber: txReceipt.blockNumber,
      gasUsed: txReceipt.gasUsed,
    };
  }

  /**
   * Internal: poll until targetConfirmations blocks have been mined since txBlock.
   */
  private async _waitForConfirmations(
    txBlock: number,
    targetConfirmations: number
  ): Promise<void> {
    const POLL_INTERVAL_MS = 500;

    return new Promise<void>((resolve, reject) => {
      const startTime = Date.now();
      const TIMEOUT_MS = 300_000; // 5 minute timeout

      const interval = setInterval(async () => {
        try {
          const currentBlock = await this.provider.getBlockNumber();
          const confirmations = currentBlock - txBlock + 1;

          if (confirmations >= targetConfirmations) {
            clearInterval(interval);
            resolve();
          }

          if (Date.now() - startTime > TIMEOUT_MS) {
            clearInterval(interval);
            reject(
              new Error(
                `Timeout waiting for ${targetConfirmations} confirmations ` +
                `(got ${confirmations} after ${TIMEOUT_MS / 1000}s)`
              )
            );
          }
        } catch (err) {
          clearInterval(interval);
          reject(err);
        }
      }, POLL_INTERVAL_MS);
    });
  }
}
