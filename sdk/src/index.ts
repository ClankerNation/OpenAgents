import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface EventSubscriptionOptions {
  indexedFilters?: Record<string, unknown>;
  autoReconnect?: boolean;
  reconnectDelayMs?: number;
}

export interface DecodedEvent {
  name: string;
  args: Record<string, unknown>;
  values: unknown[];
  log: any;
}

export interface EventSubscription {
  unsubscribe: () => void;
  resubscribe: () => Promise<void>;
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

  subscribeToEvents(
    contract: ethers.Contract,
    eventName: string,
    callback: (event: DecodedEvent) => Promise<void> | void,
    options: EventSubscriptionOptions = {}
  ): EventSubscription {
    const eventFragment = contract.interface.getEvent(eventName);
    if (!eventFragment) {
      throw new Error(`Unknown event: ${eventName}`);
    }

    const indexedInputs = eventFragment.inputs.filter((input) => input.indexed);
    const filterValues = indexedInputs.map((input) => (
      options.indexedFilters && input.name in options.indexedFilters
        ? options.indexedFilters[input.name]
        : null
    ));

    const filterFactory = (contract as any).filters?.[eventName];
    const filter = filterFactory ? filterFactory(...filterValues) : eventName;

    const listener = async (...listenerArgs: unknown[]) => {
      const eventPayload = listenerArgs[listenerArgs.length - 1];
      const values = listenerArgs.slice(0, eventFragment.inputs.length);
      const args: Record<string, unknown> = {};

      eventFragment.inputs.forEach((input, index) => {
        args[input.name || String(index)] = values[index];
      });

      await callback({
        name: eventName,
        args,
        values,
        log: (eventPayload as any)?.log ?? eventPayload,
      });
    };

    const subscribe = async () => {
      await (contract as any).on(filter, listener);
    };
    const unsubscribe = () => {
      (contract as any).off(filter, listener);
    };
    const resubscribe = async () => {
      unsubscribe();
      if ((options.reconnectDelayMs ?? 1000) > 0) {
        await new Promise((resolve) => setTimeout(resolve, options.reconnectDelayMs ?? 1000));
      }
      await subscribe();
    };

    subscribe();

    if (options.autoReconnect !== false) {
      const provider = (contract.runner as any)?.provider ?? (contract as any).provider ?? this.provider;
      const websocket = (provider as any)?.websocket ?? (provider as any)?._websocket;
      if (websocket?.addEventListener) {
        websocket.addEventListener("close", resubscribe);
      } else if (websocket?.on) {
        websocket.on("close", resubscribe);
      } else if ((provider as any)?.on) {
        (provider as any).on("disconnect", resubscribe);
      }
    }

    return { unsubscribe, resubscribe };
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
}
