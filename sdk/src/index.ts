// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
import { ethers } from "ethers";

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
   * Deploy a contract with constructor arguments and wait for confirmation.
   * @param bytecode Contract bytecode (hex string)
   * @param abi Contract ABI for encoding constructor args
   * @param args Constructor arguments array
   * @param overrides Optional transaction overrides (gasLimit, value, etc.)
   * @returns Deployed contract address
   */
  async deployContract(
    bytecode: string,
    abi: any[],
    args: any[] = [],
    overrides?: ethers.Overrides
  ): Promise<string> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args, overrides || {});
    await contract.waitForDeployment();
    return contract.target as string;
  }

  /**
   * Encode constructor arguments for manual deployment or verification.
   * @param abi Contract ABI
   * @param args Constructor arguments
   * @returns Encoded constructor data (hex)
   */
  encodeConstructorArgs(abi: any[], args: any[]): string {
    const iface = new ethers.Interface(abi);
    const fragment = iface.deploy;
    if (!fragment) return "0x";
    return iface.encodeDeploy(args);
  }

  /**
   * Wait for a transaction to be mined with configurable confirmations.
   * @param txHash Transaction hash to wait for
   * @param confirmations Number of block confirmations (default: 1)
   * @returns Transaction receipt
   */
  async waitForTransaction(
    txHash: string,
    confirmations: number = 1
  ): Promise<ethers.TransactionReceipt> {
    const receipt = await this.provider.waitForTransaction(txHash, confirmations);
    if (!receipt) throw new Error("Transaction receipt not found");
    return receipt;
  }
}
