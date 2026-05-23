import { ethers } from "ethers";
import { EventEmitter } from "events";

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

  async getOpenTasks(offset: number = 0, limit: number = 50): Promise<any[]> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );

    const count = await router.taskCount();
    const openTasks: any[] = [];
    const end = Math.min(offset + limit, Number(count));
    const batchSize = 10;

    for (let start = offset; start < end; start += batchSize) {
      const batchEnd = Math.min(start + batchSize, end);
      const batch = [];
      for (let i = start; i < batchEnd; i++) {
        batch.push(router.tasks(i));
      }
      const results = await Promise.all(batch);
      for (let j = 0; j < results.length; j++) {
        const task = results[j];
        if (task[5] === 0) {
          openTasks.push({
            id: start + j,
            creator: task[0],
            description: task[2],
            reward: task[3],
            deadline: task[4],
          });
        }
      }
    }

    return openTasks;
  }

  async subscribeToEvents(
    contractAddress: string,
    abi: string[],
    eventName: string,
    callback: (...args: unknown[]) => void
  ): Promise<ethers.Contract> {
    const contract = new ethers.Contract(contractAddress, abi, this.provider);
    contract.on(eventName, callback);
    return contract;
  }

  async decodeEventLog(
    abi: string[],
    data: string,
    topics: string[]
  ): Promise<ethers.LogDescription | null> {
    try {
      const iface = new ethers.Interface(abi);
      return iface.parseLog({ data, topics });
    } catch {
      return null;
    }
  }

  async getContractEvents(
    contractAddress: string,
    abi: string[],
    eventName: string,
    fromBlock: number,
    toBlock: number = fromBlock
  ): Promise<ethers.LogDescription[]> {
    const contract = new ethers.Contract(contractAddress, abi, this.provider);
    const filter = contract.filters[eventName]();
    const logs = await this.provider.getLogs({
      address: contractAddress,
      topic: filter?.topic,
      fromBlock,
      toBlock,
    });
    const iface = new ethers.Interface(abi);
    return logs.map((log) => iface.parseLog(log)).filter((l): l is ethers.LogDescription => l !== null);
  }
}
