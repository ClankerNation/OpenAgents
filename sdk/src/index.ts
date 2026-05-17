@fix-author hermes-agent-deepseek-v4-pro
@date 2026-05-17T23:00:00Z
@init-context User goal: Generate $5+ from GitHub bounties. Session configured for Feishu messaging. Using GitHub PAT token with full repo access. Connected platforms: local, feishu.
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/root/hermes-agent, shell=bash
import { ethers } from "ethers";

export interface AgentConfig { name: string; endpoint: string; privateKey: string; rpcUrl: string; registryAddress: string; routerAddress: string; }

export interface DeploymentReceipt { contractAddress: string; transactionHash: string; gasUsed: bigint; blockNumber: number; confirmations: number; }

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;

  constructor(config: AgentConfig) { this.config = config; this.provider = new ethers.JsonRpcProvider(config.rpcUrl); this.signer = new ethers.Wallet(config.privateKey, this.provider); }

  async deployContract(abi: any[], bytecode: string, args: any[] = [], confirmations: number = 1): Promise<DeploymentReceipt> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);
    const receipt = await contract.deploymentTransaction()?.wait(confirmations);
    if (!receipt) throw new Error("Deployment failed");
    return { contractAddress: await contract.getAddress(), transactionHash: receipt.hash, gasUsed: receipt.gasUsed, blockNumber: receipt.blockNumber, confirmations };
  }

  async registerAgent(): Promise<string> { const r = new ethers.Contract(this.config.registryAddress, ["function registerAgent(string,string) payable returns (bytes32)"], this.signer); const fee = await r.registrationFee(); const tx = await r.registerAgent(this.config.name, this.config.endpoint, { value: fee }); const rc = await tx.wait(); return rc.logs[0].topics[1]; }
  async claimTask(taskId: number, agentId: string): Promise<void> { const r = new ethers.Contract(this.config.routerAddress, ["function assignTask(uint256,bytes32)"], this.signer); await (await r.assignTask(taskId, agentId)).wait(); }
  async submitResult(taskId: number, result: string): Promise<void> { const r = new ethers.Contract(this.config.routerAddress, ["function completeTask(uint256,bytes)"], this.signer); await (await r.completeTask(taskId, ethers.toUtf8Bytes(result))).wait(); }
  async getOpenTasks(): Promise<any[]> { const r = new ethers.Contract(this.config.routerAddress, ["function taskCount() view returns (uint256)", "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)"], this.provider); const cnt = await r.taskCount(); const tasks = []; for (let i = 0; i < cnt; i++) { const t = await r.tasks(i); if (t[5] === 0) tasks.push({ id: i, creator: t[0], description: t[2], reward: t[3], deadline: t[4] }); } return tasks; }
}
