import { ethers } from "ethers";

/**
 * Result of a successful contract deployment.
 */
export interface DeployResult {
  address: string;
  txHash: string;
  gasUsed: bigint;
  contract: ethers.Contract;
}

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

  async deployContract(
    abi: ethers.Interface | Array<ethers.Fragment | string | object>,
    bytecode: string,
    args: unknown[] = [],
    confirmations: number = 1
  ): Promise<DeployResult> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const deployed = await factory.deploy(...args);
    const tx = deployed.deploymentTransaction();
    if (!tx) throw new Error("Deployment transaction not available");

    const receipt = await tx.wait(confirmations);
    const address = await deployed.getAddress();

    return {
      address,
      txHash: tx.hash,
      gasUsed: receipt?.gasUsed ?? 0n,
      contract: deployed,
    };
  }

  async subscribeToEvents(
    contractAddress: string,
    abi: ethers.Interface | Array<ethers.Fragment | string | object>,
    eventName: string,
    callback: (...args: any[]) => void,
    filter?: Record<string, string>
  ): Promise<() => void> {
    const iface = abi instanceof ethers.Interface ? abi : new ethers.Interface(abi);
    const eventFragment = iface.getEvent(eventName);
    if (!eventFragment) throw new Error(`Event "${eventName}" not found in ABI`);

    const topic = iface.getEventTopic(eventFragment);
    const topicFilters: (string | null)[] = [topic];

    if (filter) {
      const inputs = eventFragment.inputs;
      for (let i = 0; i < inputs.length; i++) {
        if (inputs[i].indexed) {
          const filterKey = inputs[i].name;
          topicFilters.push(filter[filterKey] ? ethers.id(filter[filterKey].toLowerCase()) : null);
        }
      }
    }

    const wsUrl = this.config.rpcUrl.replace("https://", "wss://").replace("http://", "ws://");
    const { WebSocketProvider } = await import("../providers/websocket");
    const wsProvider = new WebSocketProvider({ url: wsUrl });
    await wsProvider.connect();

    const subId = await wsProvider.subscribe("logs", (logData: any) => {
      try {
        const parsed = iface.parseLog({
          topics: logData.topics ?? [],
          data: logData.data ?? "0x",
        });
        if (parsed && parsed.name === eventName) {
          callback(...parsed.args.map((a: any) => a));
        }
      } catch {
        // Ignore non-matching logs
      }
    }, {
      address: [contractAddress],
      topics: topicFilters,
    });

    return () => {
      wsProvider.unsubscribe(subId).catch(() => {});
      wsProvider.disconnect();
    };
  }
}
