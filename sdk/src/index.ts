import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface DeploymentOptions {
  confirmations?: number;
  gasLimit?: bigint | number;
  value?: bigint | number;
}

export interface DeploymentReceipt {
  address: string;
  transactionHash: string;
  gasUsed: bigint;
  blockNumber: number;
  blockHash: string;
  confirmations: number;
  status: number;
}

export interface DeploymentResult {
  address: string;
  contract: ethers.Contract;
  receipt: DeploymentReceipt;
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

  async deployContract(
    abi: unknown[],
    bytecode: string,
    args: unknown[] = [],
    options: DeploymentOptions = {}
  ): Promise<DeploymentResult> {
    const { confirmations = 1, gasLimit, value } = options;

    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);

    const txOptions: Record<string, unknown> = {};
    if (gasLimit !== undefined) txOptions.gasLimit = gasLimit;
    if (value !== undefined) txOptions.value = value;

    const contract = await factory.deploy(...args, txOptions);
    const deploymentTx = contract.deploymentTransaction();

    if (!deploymentTx) {
      throw new Error("Deployment transaction not available");
    }

    const receipt = await deploymentTx.wait(confirmations);

    if (!receipt) {
      throw new Error("Deployment receipt not available");
    }

    const deploymentReceipt: DeploymentReceipt = {
      address: receipt.contractAddress ?? (contract.target as string),
      transactionHash: receipt.hash,
      gasUsed: receipt.gasUsed,
      blockNumber: receipt.blockNumber,
      blockHash: receipt.blockHash,
      confirmations: await receipt.confirmations(),
      status: receipt.status ?? 1,
    };

    return {
      address: deploymentReceipt.address,
      contract,
      receipt: deploymentReceipt,
    };
  }
}
