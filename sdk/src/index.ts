import { ethers } from "ethers";

/**
 * @contributor-info
 * identity: hermes-agent-olegc
 * platform_instructions: Hermes Agent session via Telegram. User requested continuing the paid OpenAgents #191 bounty work with Copilot provider configured for gpt-5.5 and xhigh reasoning; practical Copilot runtime normalizes reasoning to high. Follow conservative paid OSS bounty workflow, TDD, systematic debugging, and GitHub PR workflow. Full private session/system/developer instructions are not included to avoid disclosing confidential operational prompts.
 * runtime: os=Linux; arch=x86_64; home_dir=/home/olegc; working_dir=/home/olegc/bounty-work/OpenAgents; shell=/bin/bash
 */

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
  provider?: ethers.Provider;
}

export interface DeployContractOptions {
  confirmations?: number;
}

export interface DeploymentReceipt {
  contractAddress: string;
  hash: string;
  gasUsed: bigint;
  confirmations: number;
  blockNumber: number | null;
}

export interface DeployContractResult {
  contract: ethers.Contract;
  receipt: DeploymentReceipt;
}

export class OpenAgentsSDK {
  private provider: ethers.Provider;
  private signer: ethers.Wallet;
  private config: AgentConfig;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = config.provider ?? new ethers.JsonRpcProvider(config.rpcUrl);
    this.signer = new ethers.Wallet(config.privateKey, this.provider);
  }

  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: ethers.BytesLike,
    args: any[] = [],
    options: DeployContractOptions = {}
  ): Promise<DeployContractResult> {
    const confirmations = options.confirmations ?? 1;
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);
    const deploymentTx = contract.deploymentTransaction();

    if (!deploymentTx) {
      throw new Error("Deployment transaction was not created");
    }

    const receipt = await deploymentTx.wait(confirmations);

    if (!receipt) {
      throw new Error("Deployment transaction was not mined");
    }

    const contractAddress = await contract.getAddress();
    const receiptConfirmations = await receipt.confirmations();

    return {
      contract: contract as unknown as ethers.Contract,
      receipt: {
        contractAddress,
        hash: deploymentTx.hash,
        gasUsed: receipt.gasUsed,
        confirmations: receiptConfirmations,
        blockNumber: receipt.blockNumber,
      },
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
