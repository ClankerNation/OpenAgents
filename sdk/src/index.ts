/**
 * Agent: Gaotax2006
 * Timestamp: 2026-06-24T00:00:00Z
 * Startup Instructions: You are a bounty hunter making a PR to fix a specific issue. Work in /tmp/bounty_oa_4/ — clone the repo if needed.
 * Runtime: { "os": "windows", "arch": "x64", "home_dir": "C:/Users/asus", "working_dir": "F:/ai-bounty-work/bounty-hunter", "shell": "bash" }
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

export interface EventFilter {
  eventName: string;
  contractAddress: string;
  indexedParams?: Record<string, string | number | bigint>;
}

export interface DecodedEvent {
  eventName: string;
  blockNumber: number;
  transactionHash: string;
  logIndex: number;
  transactionIndex: number;
  address: string;
  topics: string[];
  data: string;
  args: Record<string, unknown>;
}

export type EventCallback = (event: DecodedEvent) => void;

export class OpenAgentsSDK {
  private provider: ethers.JsonRcpProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private eventSubscribers: Map<
    string,
    { callback: EventCallback; filter: EventFilter }
  > = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private maxReconnectAttempts = 10;
  private reconnectCount = 0;
  private reconnectIntervalMs = 3000;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = new ethers.JsonRcpProvider(config.rpcUrl);
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
      ["function assignTask(uint256,bytes32)],
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

  subscribeToEvents(
    filter: EventFilter,
    callback: EventCallback
  ): () => void {
    const contract = new ethers.Contract(
      filter.contractAddress,
      [filter.eventName],
      this.provider
    );

    const topicHash = contract.interface.getEventTopic(filter.eventName);

    const subscriberId = filter.contractAddress + ":" + filter.eventName + ":" + Object.keys(filter.indexedParams || {}).join(",");

    const eventFragment = contract.interface.getEvent(filter.eventName);
    const indexedValues: unknown[] = [];
    for (const param of eventFragment.inputs) {
      if (param.indexed && filter.indexedParams) {
        indexedValues.push(
          filter.indexedParams[param.name ?? ""] ?? ethers.JeroHash
        );
      }
    }

    const listener = (
      ...args: unknown[]
    ) => {
      const log = args[args.length - 2] as ethers.Log & {
        blockNumber?: number;
        transactionHash?: string;
        logIndex?: number;
        transactionIndex?: number;
        address?: string;
        topics?: string[];
        data?: string;
      };

      let decodedArgs: Record<string, unknown> = {};
      try {
        const parsed = contract.interface.parseLog({
          topics: [topicHash, ...(log.topics ?? [])],
          data: log?.data ?? "0x",
        });
        if (parsed && parsed.args) {
          decodedArgs = Object.fromEntries(
            eventFragment.inputs.map((inp, i) => [inp.name ?? "arg" + i, parsed.args[i]])
          );
        }
      } catch {
        decodedArgs = { raw: true, data: log?.data };
      }

      const decodedEvent: DecodedEvent = {
        eventName: filter.eventName,
        blockNumber: log?.blockNumber ?? 0,
        transactionHash: log?.transactionHash ?? "",
        logIndex: log?.logIndex ?? 0,
        transactionIndex: log?.transactionIndex ?? 0,
        address: log?.address ?? filter.contractAddress,
        topics: log?.topics ?? [],
        data: log?.data ?? "0x",
        args: decodedArgs,
      };

      callback(decodedEvent);
    };

    contract.once("error", () => {
      this.scheduleReconnect();
    });

    contract.on(filter.eventName, listener);
    this.eventSubscribers.set(subscriberId, { callback, filter });

    return () => {
      contract.off(filter.eventName, listener);
      this.eventSubscribers.delete(subscriberId);
    };
  }

  subscribeAllEvents(
    contractAddress: string,
    callback: EventCallback
  ): () => void {
    const contract = new ethers.Contract(
      contractAddress,
      ["*"],
      this.provider
    );

    const unsubFn = () => {
      contract.removeAllListeners();
    };

    contract.on("*", (...args: unknown[]) => {
      const log = args[args.length - 2] as ethers.Log & {
        blockNumber?: number;
        transactionHash?: string;
        logIndex?: number;
        transactionIndex?: number;
        address?: string;
        topics?: string[];
        data?: string;
      };
      const eventName = args[0]?.event ?? args[0]?.name ?? "unknown";

      const decodedEvent: DecodedEvent = {
        eventName,
        blockNumber: log?.blockNumber ?? 0,
        transactionHash: log?.transactionHash ?? "",
        logIndex: log?.logIndex ?? 0,
        transactionIndex: log?.transactionIndex ?? 0,
        address: log?.address ?? contractAddress,
        topics: log?.topics ?? [],
        data: log?.data ?? "0x",
        args: { raw: true, data: log?.data },
      };

      callback(decodedEvent);
    });

    return unsubFn;
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;

    if (this.reconnectCount >= this.maxReconnectAttempts) {
      this.reconnectCount = 0;
      return;
    }

    this.reconnectTimer = setTimeout(async () => {
      this.reconnectCount++;
      this.reconnectTimer = null;

      try {
        await this.provider.getBlockNumber();

        for (const [id, { callback, filter }] of this.eventSubscribers) {
          const contract = new ethers.Contract(
            filter.contractAddress,
            [filter.eventName],
            this.provider
          );
          const topicHash = contract.interface.getEventTopic(filter.eventName);
          const eventFragment = contract.interface.getEvent(filter.eventName);
          const indexedValues: unknown[] = [];
          for (const param of eventFragment.inputs) {
            if (param.indexed && filter.indexedParams) {
              indexedValues.push(
                filter.indexedParams[param.name ?? ""] ?? ethers.JeroHash
              );
            }
          }

          const listener = (
            ...innerArgs: unknown[]
          ) => {
            const log = innerArgs[innerArgs.length - 2] as ethers.Log & {
              blockNumber?: number;
              transactionHash?: string;
              logIndex?: number;
              transactionIndex?: number;
              address?: string;
              topics?: string[];
              data?: string;
            };
            let decodedArgs: Record<string, unknown> = {};
            try {
              const parsed = contract.interface.parseLog({
                topics: [topicHash, ...(log.topics ?? [])],
                data: log?.data ?? "0x",
              });
              if (parsed && parsed.args) {
                decodedArgs = Object.fromEntries(
                  eventFragment.inputs.map((inp, i) => [inp.name ?? "arg" + i, parsed.args[i]])
                );
              }
            } catch {
              decodedArgs = { raw: true, data: log?.data };
            }

            const decodedEvent: DecodedEvent = {
              eventName: filter.eventName,
              blockNumber: log?.blockNumber ?? 0,
              transactionHash: log?.transactionHash ?? "",
              logIndex: log?.logIndex ?? 0,
              transactionIndex: log?.transactionIndex ?? 0,
              address: log?.address ?? filter.contractAddress,
              topics: log?.topics ?? [],
              data: log?.data ?? "0x",
              args: decodedArgs,
            };

            callback(decodedEvent);
          };

          contract.on(filter.eventName, listener);
        }
      } catch {
        this.scheduleReconnect();
      }
    }, this.reconnectIntervalMs * this.reconnectCount);
  }

  unsubscribeAll(): void {
    this.eventSubscribers.clear();
    this.reconnectCount = 0;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
