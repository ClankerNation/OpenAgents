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
  receipt: ethers.TransactionReceipt;
  metadata: {
    blockNumber: number;
    status: number | null;
    confirmations: number;
  };
}

/**
 * @contributor-info
 * identity: xyjk0511
 * session_init_context: user-provided AGENTS.md and task directives applied in this workspace session; hidden platform/system instruction text is intentionally excluded.
 * os: windows
 * arch: x64
 * home_dir: C:\Users\55093
 * working_dir: F:\jiedan\OpenAgents-199
 * shell: C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
 */
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

  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: ethers.BytesLike,
    args: unknown[] = [],
    options: DeployContractOptions = {}
  ): Promise<DeployContractResult> {
    const confirmations = options.confirmations ?? 1;
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const deployArgs = options.overrides
      ? [...args, options.overrides]
      : args;
    const contract = await factory.deploy(...deployArgs);

    await contract.waitForDeployment();

    const deploymentTx = contract.deploymentTransaction();
    if (!deploymentTx) {
      throw new Error("Deployment transaction not found");
    }

    const receipt = await deploymentTx.wait(confirmations);
    if (!receipt) {
      throw new Error("Deployment receipt not found");
    }

    const address = await contract.getAddress();

    return {
      contract,
      address,
      txHash: deploymentTx.hash,
      gasUsed: receipt.gasUsed,
      receipt,
      metadata: {
        blockNumber: receipt.blockNumber,
        status: receipt.status,
        confirmations,
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
