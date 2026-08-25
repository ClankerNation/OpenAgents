import { ethers } from "ethers";

// @fix-author rafaio1
// @date 2026-08-25T00:00:00Z
// @runtime linux x64 /tmp/openagents_issue_199 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface DeployResult {
  address: string;
  txHash: string;
  blockNumber: number;
  gasUsed: bigint;
}

export interface DeploymentOptions {
  overrides?: ethers.Overrides;
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

  /**
   * Deploy a contract from ABI and bytecode with constructor arguments
   * @param abi Contract ABI (ethers compatible format)
   * @param bytecode Contract creation bytecode (hex string)
   * @param args Constructor arguments
   * @param options Optional deployment overrides and confirmation count
   * @returns DeployResult with deployed address and transaction details
   */
  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: string,
    args: unknown[] = [],
    options: DeploymentOptions = {}
  ): Promise<DeployResult> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    
    const contract = await factory.deploy(...args, {
      ...options.overrides,
    });
    
    const receipt = await contract.deploymentTransaction()?.wait(options.confirmations ?? 1);
    
    if (!receipt || !contract.target) {
      throw new Error("Deployment failed: no receipt or contract address");
    }

    return {
      address: contract.target as string,
      txHash: receipt.hash,
      blockNumber: receipt.blockNumber,
      gasUsed: receipt.gasUsed,
    };
  }

  /**
   * Get a typed contract instance for an already-deployed contract
   * @param address Deployed contract address
   * @param abi Contract ABI
   * @param useSigner If true, returns signer-connected contract; otherwise provider-only
   */
  getContract(address: string, abi: ethers.InterfaceAbi, useSigner: boolean = false): ethers.Contract {
    return new ethers.Contract(
      address,
      abi,
      useSigner ? this.signer : this.provider
    );
  }

  /**
   * Verify that a contract is deployed at the expected address by checking code size
   * @param address Address to verify
   * @returns true if contract code exists at address
   */
  async isContractDeployed(address: string): Promise<boolean> {
    const code = await this.provider.getCode(address);
    return code !== "0x" && code.length > 2;
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
