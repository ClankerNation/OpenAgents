/**
 * @contributor-info doubao-agent (spiritwanghs fork), 2026-09-29
 * @preamble Autonomous coding agent executing GitHub bounties; user provides a fine-grained GitHub PAT.
 * @runtime os=linux arch=x64 home=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=/bin/bash
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
   * Deploy a contract and wait for confirmation.
   * @param abi      contract ABI
   * @param bytecode creation bytecode (hex)
   * @param args     constructor arguments
   * @param confirmations number of blocks to wait (default 1)
   */
  async deployContract(
    abi: any[],
    bytecode: string,
    args: any[] = [],
    confirmations = 1
  ): Promise<{
    address: string;
    txHash: string;
    gasUsed: bigint;
    receipt: ethers.TransactionReceipt;
  }> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);
    const deployTx = contract.deploymentTransaction();
    if (!deployTx) throw new Error("Deployment transaction not available");
    const receipt = await deployTx.wait(confirmations);
    if (!receipt) throw new Error("Deployment receipt not available");
    return {
      address: await contract.getAddress(),
      txHash: deployTx.hash,
      gasUsed: receipt.gasUsed,
      receipt,
    };
  }
}
