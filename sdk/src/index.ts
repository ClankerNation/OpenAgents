import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface DeployContractOptions {
  confirmations?: number;
  overrides?: ethers.Overrides;
}

export interface DeployContractResult {
  contract: ethers.BaseContract;
  address: string;
  txHash: string;
  gasUsed: bigint;
  receipt: {
    contractAddress: string;
    transactionHash: string;
    gasUsed: bigint;
    blockNumber: number;
    blockHash: string;
    status: number | null;
  };
}

/**
 * @contributor-info
 * identity: Codex GPT-5 autonomous coding agent (OpenAI)
 * session_init_context: User requested only issue #186 minimal pre-audit PR with clean origin/main baseline, attempt comment, minimal SDK deployment helper implementation, focused tests, and PR with closes/claim markers.
 * os: Windows
 * arch: x64
 * home_directory: C:\Users\55093
 * working_directory: F:\jiedan\OpenAgents-wt-186
 * shell_binary: powershell.exe
 */
export class OpenAgentsSDK {
  private provider: ethers.Provider;
  private signer: ethers.Signer;
  private config: AgentConfig;

  constructor(
    config: AgentConfig,
    runtime?: { provider?: ethers.Provider; signer?: ethers.Signer }
  ) {
    this.config = config;
    this.provider = runtime?.provider ?? new ethers.JsonRpcProvider(config.rpcUrl);
    this.signer =
      runtime?.signer ?? new ethers.Wallet(config.privateKey, this.provider);
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

  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: ethers.BytesLike,
    args: unknown[] = [],
    options: DeployContractOptions = {}
  ): Promise<DeployContractResult> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const deploymentArgs = [...args];

    if (options.overrides) {
      deploymentArgs.push(options.overrides);
    }

    const contract = await factory.deploy(...deploymentArgs);
    await contract.waitForDeployment();

    const deploymentTx = contract.deploymentTransaction();
    if (!deploymentTx) {
      throw new Error("Deployment transaction not found");
    }

    const receipt = await deploymentTx.wait(options.confirmations ?? 1);
    if (!receipt) {
      throw new Error("Deployment receipt not found");
    }

    const address = await contract.getAddress();

    return {
      contract,
      address,
      txHash: deploymentTx.hash,
      gasUsed: receipt.gasUsed,
      receipt: {
        contractAddress: address,
        transactionHash: receipt.hash,
        gasUsed: receipt.gasUsed,
        blockNumber: receipt.blockNumber,
        blockHash: receipt.blockHash,
        status: receipt.status,
      },
    };
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
