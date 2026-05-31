import { ethers } from "ethers";
import { WebSocketProvider } from "./providers/websocket";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface EventContractConfig {
  address: string;
  abi?: ethers.InterfaceAbi;
}

export interface EventSubscriptionOptions {
  abi?: ethers.InterfaceAbi;
  indexedFilters?: Record<string, unknown>;
  wsUrl?: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}

export interface DecodedEventLog {
  contract: string;
  eventName: string;
  signature: string;
  args: Record<string, unknown>;
  raw: unknown;
}

interface RawEventLog {
  address: string;
  topics: string[];
  data: string;
}

/**
 * @contributor-info
 * contributor_identity: Codex (GPT-5)
 * pre_task_context_verbatim_user_side: AGENTS.md instructions for F:\\jiedan + workspace environment context + task directive.
 * pre_task_context_payload: "负责 OpenAgents #144（Add event subscription and decoding to OpenAgentsSDK）。仓库 F:\\jiedan\\OpenAgents。只做 #144。分支 c53d-144-events。按 AC 实现+最小测试；issue 评论 /attempt #144；PR 包含 /claim #144；回传证据。"
 * os: Microsoft Windows 10.0.22631
 * processor_architecture: X64
 * home_directory: C:\\Users\\55093
 * working_directory: F:\\jiedan\\OpenAgents
 * shell_binary_path: C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe
 */
export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private wsProvider: WebSocketProvider | null = null;
  private wsConnectPromise: Promise<void> | null = null;
  private wsUrlInUse: string | null = null;

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

  private resolveWsUrl(explicitUrl?: string): string {
    if (explicitUrl) {
      return explicitUrl;
    }
    if (this.config.rpcUrl.startsWith("ws://") || this.config.rpcUrl.startsWith("wss://")) {
      return this.config.rpcUrl;
    }
    if (this.config.rpcUrl.startsWith("https://")) {
      return `wss://${this.config.rpcUrl.slice("https://".length)}`;
    }
    if (this.config.rpcUrl.startsWith("http://")) {
      return `ws://${this.config.rpcUrl.slice("http://".length)}`;
    }
    throw new Error("Unable to derive WebSocket URL from rpcUrl; pass options.wsUrl explicitly");
  }

  private async getWsProvider(options: EventSubscriptionOptions): Promise<WebSocketProvider> {
    const resolvedUrl = this.resolveWsUrl(options.wsUrl);
    if (!this.wsProvider || this.wsUrlInUse !== resolvedUrl) {
      this.wsProvider?.disconnect();
      this.wsProvider = new WebSocketProvider({
        url: resolvedUrl,
        reconnectIntervalMs: options.reconnectIntervalMs,
        maxReconnectAttempts: options.maxReconnectAttempts,
      });
      this.wsUrlInUse = resolvedUrl;
      this.wsConnectPromise = null;
    }

    if (!this.wsProvider.isReady()) {
      if (!this.wsConnectPromise) {
        this.wsConnectPromise = this.wsProvider.connect().finally(() => {
          this.wsConnectPromise = null;
        });
      }
      await this.wsConnectPromise;
    }

    return this.wsProvider;
  }

  private resolveContractConfig(
    contract: string | EventContractConfig,
    options: EventSubscriptionOptions
  ): { address: string; abi: ethers.InterfaceAbi } {
    if (typeof contract === "string") {
      if (!options.abi) {
        throw new Error("ABI is required when contract is provided as address string");
      }
      return { address: contract, abi: options.abi };
    }

    const abi = contract.abi ?? options.abi;
    if (!abi) {
      throw new Error("ABI is required to decode event logs");
    }
    return { address: contract.address, abi };
  }

  private buildIndexedFilterValues(
    fragment: ethers.EventFragment,
    indexedFilters?: Record<string, unknown>
  ): unknown[] {
    const values: unknown[] = [];

    for (const input of fragment.inputs) {
      if (!input.indexed) {
        continue;
      }
      if (indexedFilters && Object.prototype.hasOwnProperty.call(indexedFilters, input.name)) {
        values.push(indexedFilters[input.name]);
      } else {
        values.push(null);
      }
    }

    return values;
  }

  private decodeNamedArgs(
    fragment: ethers.EventFragment,
    args: ethers.Result
  ): Record<string, unknown> {
    const decoded: Record<string, unknown> = {};
    let positionalIndex = 0;

    for (const input of fragment.inputs) {
      const value = args[positionalIndex++];
      if (input.name && input.name.length > 0) {
        decoded[input.name] = value;
      }
    }

    return decoded;
  }

  async subscribeToEvents(
    contract: string | EventContractConfig,
    eventName: string,
    callback: (event: DecodedEventLog) => void,
    options: EventSubscriptionOptions = {}
  ): Promise<string> {
    const { address, abi } = this.resolveContractConfig(contract, options);
    const iface = new ethers.Interface(abi);
    const fragment = iface.getEvent(eventName);

    const indexedValues = this.buildIndexedFilterValues(fragment, options.indexedFilters);
    const topics = iface.encodeFilterTopics(fragment, indexedValues);

    const wsProvider = await this.getWsProvider(options);

    return wsProvider.subscribe([
      "logs",
      {
        address,
        topics,
      },
    ], (raw) => {
      const log = raw as RawEventLog;
      if (!log || !Array.isArray(log.topics) || typeof log.data !== "string") {
        return;
      }

      const parsed = iface.parseLog({
        topics: log.topics,
        data: log.data,
      });

      if (!parsed || parsed.name !== fragment.name) {
        return;
      }

      callback({
        contract: address,
        eventName: parsed.name,
        signature: parsed.signature,
        args: this.decodeNamedArgs(fragment, parsed.args),
        raw,
      });
    });
  }

  async unsubscribeFromEvents(subscriptionId: string): Promise<boolean> {
    if (!this.wsProvider) {
      return false;
    }
    return this.wsProvider.unsubscribe(subscriptionId);
  }

  disconnectEventStream(): void {
    this.wsProvider?.disconnect();
    this.wsProvider = null;
    this.wsConnectPromise = null;
    this.wsUrlInUse = null;
  }
}
