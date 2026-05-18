import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  wsUrl?: string;
  registryAddress: string;
  routerAddress: string;
}

export interface EventCallback {
  (event: Record<string, unknown>): void;
}

interface Subscription {
  id: string;
  contract: string;
  eventName: string;
  callback: EventCallback;
  filter?: Record<string, unknown>;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private wsSocket: WebSocket | null = null;
  private subscriptions: Map<string, Subscription> = new Map();
  private subscriptionId = 0;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private wsUrl: string;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = new ethers.JsonRpcProvider(config.rpcUrl);
    this.signer = new ethers.Wallet(config.privateKey, this.provider);
    this.wsUrl = config.wsUrl || config.rpcUrl.replace(/^http/, "ws");
  }

  async subscribeToEvents(
    contract: ethers.Contract,
    eventName: string,
    callback: EventCallback,
    filter?: Record<string, unknown>
  ): Promise<string> {
    const subId = `sub_${++this.subscriptionId}`;

    const subscription: Subscription = {
      id: subId,
      contract: contract.target as string,
      eventName,
      callback,
      filter,
    };

    this.subscriptions.set(subId, subscription);

    if (!this.wsSocket || this.wsSocket.readyState !== WebSocket.OPEN) {
      await this._connectWebSocket();
    }

    const filterParams = filter ? Object.entries(filter).map(([k, v]) => ({ topics: [k, v] })) : [];
    const ethSubscribe = {
      jsonrpc: "2.0",
      id: subId,
      method: "eth_subscribe",
      params: filterParams.length > 0
        ? ["logs", { address: contract.target, topics: filterParams.map(f => f.topics) }]
        : ["logs", { address: contract.target }],
    };

    this.wsSocket?.send(JSON.stringify(ethSubscribe));
    return subId;
  }

  private async _connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.wsSocket = new WebSocket(this.wsUrl);

        this.wsSocket.onopen = () => {
          this.reconnectAttempts = 0;
          // Re-subscribe all existing subscriptions
          for (const [id, sub] of this.subscriptions) {
            const ethSubscribe = {
              jsonrpc: "2.0",
              id,
              method: "eth_subscribe",
              params: ["logs", { address: sub.contract }],
            };
            this.wsSocket?.send(JSON.stringify(ethSubscribe));
          }
          resolve();
        };

        this.wsSocket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.params?.result) {
              const decoded = this._decodeEventLog(data.params.result);
              // Find matching subscription and call callback
              for (const sub of this.subscriptions.values()) {
                if (decoded.name === sub.eventName) {
                  sub.callback(decoded);
                }
              }
            }
          } catch {
            // Ignore parse errors for non-JSON messages
          }
        };

        this.wsSocket.onerror = (error) => {
          console.error("WebSocket error:", error);
        };

        this.wsSocket.onclose = () => {
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => this._connectWebSocket(), 1000 * this.reconnectAttempts);
          }
        };
      } catch (err) {
        reject(err);
      }
    });
  }

  private _decodeEventLog(log: Record<string, unknown>): Record<string, unknown> {
    const topics = log.topics as string[];
    const data = log.data as string;

    return {
      transactionHash: log.transactionHash,
      blockNumber: log.blockNumber,
      address: log.address,
      name: topics[0],
      args: this._parseLogData(topics, data),
    };
  }

  private _parseLogData(topics: string[], data: string): Record<string, unknown> {
    const args: Record<string, unknown> = {};
    // Parse indexed parameters from topics (skip event signature at topics[0])
    for (let i = 1; i < topics.length; i++) {
      args[`arg${i}`] = topics[i];
    }
    // Parse non-indexed data
    if (data && data !== "0x") {
      args["data"] = data;
    }
    return args;
  }

  async unsubscribe(subscriptionId: string): Promise<void> {
    const sub = this.subscriptions.get(subscriptionId);
    if (!sub) return;

    const ethUnsubscribe = {
      jsonrpc: "2.0",
      id: subscriptionId,
      method: "eth_unsubscribe",
      params: [subscriptionId],
    };

    this.wsSocket?.send(JSON.stringify(ethUnsubscribe));
    this.subscriptions.delete(subscriptionId);
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
