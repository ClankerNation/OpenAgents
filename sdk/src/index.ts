@fix-author hermes-agent-deepseek-v4-pro
@date 2026-05-17T23:00:00Z
@init-context User goal: Generate $5+ from GitHub bounties. Session configured for Feishu messaging. Using GitHub PAT token with full repo access. Connected platforms: local, feishu.
@runtime os=linux, arch=x64, home_dir=/root, working_dir=/root/hermes-agent, shell=bash
import { ethers } from "ethers";

export interface AgentConfig { name: string; endpoint: string; privateKey: string; rpcUrl: string; wsUrl?: string; registryAddress: string; routerAddress: string; }

export interface DecodedEvent { eventName: string; args: Record<string, any>; blockNumber: number; transactionHash: string; logIndex: number; }

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private wsProvider: ethers.WebSocketProvider | null = null;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private subs: Map<string, { contract: ethers.Contract; listener: any }> = new Map();

  constructor(config: AgentConfig) { this.config = config; this.provider = new ethers.JsonRpcProvider(config.rpcUrl); this.signer = new ethers.Wallet(config.privateKey, this.provider); }

  private async getWs(): Promise<ethers.WebSocketProvider> {
    if (!this.config.wsUrl) throw new Error("wsUrl not configured");
    if (!this.wsProvider) this.wsProvider = new ethers.WebSocketProvider(this.config.wsUrl);
    return this.wsProvider;
  }

  async subscribeToEvents(contractAddress: string, abi: any[], eventName: string, callback: (e: DecodedEvent) => void, filters?: Record<string, any>): Promise<() => void> {
    const ws = await this.getWs();
    const contract = new ethers.Contract(contractAddress, abi, ws);
    const handler = (...args: any[]) => {
      const log = args[args.length - 1] as ethers.EventLog;
      const decoded: DecodedEvent = { eventName: log.eventName || eventName, args: {}, blockNumber: log.blockNumber, transactionHash: log.transactionHash, logIndex: log.index };
      if (log.args) { for (const [k, v] of Object.entries(log.args)) { if (isNaN(Number(k))) decoded.args[k] = v; } }
      callback(decoded);
    };
    const f = contract.filters[eventName]?.();
    contract.on(filters ? { ...f, ...filters } : (f || eventName), handler);
    this.subs.set(contractAddress + "-" + eventName, { contract, listener: handler });
    return () => { contract.off(eventName, handler); this.subs.delete(contractAddress + "-" + eventName); };
  }

  async registerAgent(): Promise<string> { const r = new ethers.Contract(this.config.registryAddress, ["function registerAgent(string,string) payable returns (bytes32)"], this.signer); const fee = await r.registrationFee(); const tx = await r.registerAgent(this.config.name, this.config.endpoint, { value: fee }); const rc = await tx.wait(); return rc.logs[0].topics[1]; }
  async claimTask(taskId: number, agentId: string): Promise<void> { const r = new ethers.Contract(this.config.routerAddress, ["function assignTask(uint256,bytes32)"], this.signer); await (await r.assignTask(taskId, agentId)).wait(); }
  async submitResult(taskId: number, result: string): Promise<void> { const r = new ethers.Contract(this.config.routerAddress, ["function completeTask(uint256,bytes)"], this.signer); await (await r.completeTask(taskId, ethers.toUtf8Bytes(result))).wait(); }
  async getOpenTasks(): Promise<any[]> { const r = new ethers.Contract(this.config.routerAddress, ["function taskCount() view returns (uint256)", "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)"], this.provider); const cnt = await r.taskCount(); const tasks = []; for (let i = 0; i < cnt; i++) { const t = await r.tasks(i); if (t[5] === 0) tasks.push({ id: i, creator: t[0], description: t[2], reward: t[3], deadline: t[4] }); } return tasks; }
  disconnect() { if (this.wsProvider) { this.wsProvider.destroy(); this.wsProvider = null; } }
}
