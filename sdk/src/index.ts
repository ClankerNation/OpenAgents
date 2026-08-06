import { ethers } from "ethers";
import { WebSocketProvider } from "./providers/websocket";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  websocketUrl?: string;
  registryAddress: string;
  routerAddress: string;
}

export interface EventContractDefinition {
  address: string;
  abi: ethers.InterfaceAbi;
}

export type EventContract = ethers.Contract | EventContractDefinition;

export interface EventSubscriptionProvider {
  subscribe(
    event: string,
    callback: (data: unknown) => void,
    params?: unknown[]
  ): Promise<string>;
  unsubscribe(subscriptionId: string): Promise<boolean>;
}

export interface EventSubscriptionOptions {
  indexedFilters?: Record<string, unknown>;
  provider?: EventSubscriptionProvider;
  websocketUrl?: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}

export interface DecodedContractEvent {
  name: string;
  signature: string;
  args: Record<string, unknown>;
  values: unknown[];
  log: unknown;
}

export interface EventSubscription {
  id: string;
  unsubscribe(): Promise<boolean>;
}

function contractInterface(contract: EventContract): ethers.Interface {
  if (contract instanceof ethers.Contract) return contract.interface;
  return new ethers.Interface(contract.abi);
}

function contractAddress(contract: EventContract): string {
  if (contract instanceof ethers.Contract) {
    if (typeof contract.target !== "string") {
      throw new Error("Event contract must expose a concrete address");
    }
    return contract.target;
  }
  return contract.address;
}

function eventFilter(
  iface: ethers.Interface,
  fragment: ethers.EventFragment,
  address: string,
  indexedFilters: Record<string, unknown> = {}
): { address: string; topics: Array<null | string | string[]> } {
  const indexedInputs = fragment.inputs.filter((input) => input.indexed);
  const acceptedKeys = new Set(
    indexedInputs.map((input, index) => input.name || String(index)),
  );
  for (const key of Object.keys(indexedFilters)) {
    if (!acceptedKeys.has(key)) {
      throw new Error(`Unknown indexed event filter: ${key}`);
    }
  }

  const values = indexedInputs.map((input, index) => {
    const key = input.name || String(index);
    return Object.prototype.hasOwnProperty.call(indexedFilters, key)
      ? indexedFilters[key]
      : null;
  });
  const topics = iface.encodeFilterTopics(fragment, values);
  return { address, topics };
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private eventProvider: EventSubscriptionProvider | null = null;

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

  async subscribeToEvents(
    contract: EventContract,
    eventName: string,
    callback: (event: DecodedContractEvent) => void | Promise<void>,
    options: EventSubscriptionOptions = {},
  ): Promise<EventSubscription> {
    const iface = contractInterface(contract);
    let fragment: ethers.EventFragment | null;
    try {
      fragment = iface.getEvent(eventName);
    } catch (error) {
      throw new Error(`Unknown or ambiguous event: ${eventName}`, { cause: error });
    }
    if (!fragment) throw new Error(`Unknown event: ${eventName}`);

    const filter = eventFilter(iface, fragment, contractAddress(contract), options.indexedFilters);
    const provider = options.provider ?? this.getEventProvider(options);
    let active = true;
    const subscriptionId = await provider.subscribe(
      "logs",
      async (rawLog: unknown) => {
        if (!active) return;
        const log = rawLog as { topics?: unknown; data?: unknown };
        if (!Array.isArray(log.topics) || typeof log.data !== "string") {
          throw new Error(`Invalid ${eventName} log payload`);
        }
        const parsed = iface.parseLog({
          topics: log.topics as string[],
          data: log.data,
        });
        if (!parsed) return;

        const values = Array.from(parsed.args);
        const args: Record<string, unknown> = {};
        fragment.inputs.forEach((input, index) => {
          args[input.name || String(index)] = values[index];
        });
        await callback({
          name: parsed.name,
          signature: parsed.signature,
          args,
          values,
          log: rawLog,
        });
      },
      [filter],
    );

    return {
      id: subscriptionId,
      async unsubscribe(): Promise<boolean> {
        if (!active) return false;
        active = false;
        return provider.unsubscribe(subscriptionId);
      },
    };
  }

  private getEventProvider(options: EventSubscriptionOptions): EventSubscriptionProvider {
    if (this.eventProvider) return this.eventProvider;
    const url = options.websocketUrl ?? this.config.websocketUrl;
    if (!url) {
      throw new Error("subscribeToEvents requires AgentConfig.websocketUrl or options.websocketUrl");
    }
    this.eventProvider = new WebSocketProvider({
      url,
      reconnectIntervalMs: options.reconnectIntervalMs,
      maxReconnectAttempts: options.maxReconnectAttempts,
    });
    return this.eventProvider;
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
