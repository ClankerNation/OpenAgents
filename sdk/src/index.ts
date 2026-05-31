import { ethers } from "ethers";
import { WebSocketProvider } from "./providers/websocket";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  wsRpcUrl?: string;
  registryAddress: string;
  routerAddress: string;
}

export interface DecodedEventPayload {
  name: string;
  signature: string;
  args: Record<string, unknown>;
  log: any;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private wsProvider: WebSocketProvider | null = null;
  private wsConnectPromise: Promise<void> | null = null;

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

  async subscribeToEvents(
    contract: ethers.Contract,
    eventName: string,
    callback: (event: DecodedEventPayload) => void,
    indexedFilters: Record<string, unknown> = {}
  ): Promise<string> {
    const eventFragment = contract.interface.getEvent(eventName);
    const topicFilters = contract.interface.encodeFilterTopics(
      eventFragment,
      this.buildIndexedTopicValues(eventFragment, indexedFilters)
    );
    const address = await this.resolveContractAddress(contract);
    const wsProvider = await this.getWebSocketProvider();

    return wsProvider.subscribe(
      "logs",
      (rawLog) => {
        const log = rawLog as { data?: string; topics?: string[] };
        if (!log?.data || !Array.isArray(log?.topics)) return;
        try {
          const decoded = contract.interface.parseLog({
            data: log.data,
            topics: log.topics,
          });
          if (!decoded || decoded.name !== eventFragment.name) return;
          callback({
            name: decoded.name,
            signature: decoded.signature,
            args: this.toNamedArgs(decoded.fragment.inputs, decoded.args),
            log: rawLog,
          });
        } catch {
          // Ignore non-matching logs
        }
      },
      { address, topics: topicFilters }
    );
  }

  private async getWebSocketProvider(): Promise<WebSocketProvider> {
    if (!this.wsProvider) {
      this.wsProvider = new WebSocketProvider({
        url: this.toWebSocketUrl(this.config.wsRpcUrl ?? this.config.rpcUrl),
      });
      this.wsConnectPromise = this.wsProvider.connect();
    }
    if (this.wsConnectPromise) {
      await this.wsConnectPromise;
      this.wsConnectPromise = null;
    }
    return this.wsProvider;
  }

  private toWebSocketUrl(url: string): string {
    if (url.startsWith("ws://") || url.startsWith("wss://")) {
      return url;
    }
    if (url.startsWith("https://")) {
      return `wss://${url.slice("https://".length)}`;
    }
    if (url.startsWith("http://")) {
      return `ws://${url.slice("http://".length)}`;
    }
    return url;
  }

  private async resolveContractAddress(contract: ethers.Contract): Promise<string> {
    return ethers.resolveAddress(
      contract.target as ethers.AddressLike,
      this.provider
    );
  }

  private buildIndexedTopicValues(
    eventFragment: ethers.EventFragment,
    indexedFilters: Record<string, unknown>
  ): Array<unknown> {
    return eventFragment.inputs
      .filter((input) => input.indexed)
      .map((input) => (
        Object.prototype.hasOwnProperty.call(indexedFilters, input.name)
          ? indexedFilters[input.name]
          : null
      ));
  }

  private toNamedArgs(
    inputs: ReadonlyArray<ethers.ParamType>,
    args: ethers.Result
  ): Record<string, unknown> {
    const named: Record<string, unknown> = {};
    inputs.forEach((input, index) => {
      const key = input.name || index.toString();
      named[key] = args[index];
    });
    return named;
  }
}
