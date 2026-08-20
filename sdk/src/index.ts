/**
 * @contributor-info rafaio1
 * @timestamp 2026-08-20T00:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
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

export interface DeploymentReceipt {
  address: string;
  txHash: string;
  gasUsed: bigint;
  blockNumber: number;
  confirmations: number;
}

export interface EventSubscription {
  unsubscribe: () => void;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private _taskCountCache: { value: number; blockNumber: number } | null = null;
  private _wsProvider: ethers.WebSocketProvider | null = null;
  private _reconnectAttempts = 0;
  private _maxReconnectAttempts = 10;
  private _subscriptions: Map<string, { contract: ethers.Contract; eventName: string; callback: (log: any) => void; filter?: Record<string, unknown> }> = new Map();

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

  /**
   * Deploy a contract and wait for confirmation.
   */
  async deployContract(
    abi: any[],
    bytecode: string,
    args: unknown[] = [],
    confirmations: number = 1
  ): Promise<DeploymentReceipt> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);
    
    const receipt = await contract.deploymentTransaction()?.wait(confirmations);
    
    if (!receipt || !contract.target) {
      throw new Error("Deployment failed: no receipt or contract address");
    }

    return {
      address: contract.target as string,
      txHash: receipt.hash,
      gasUsed: receipt.gasUsed,
      blockNumber: receipt.blockNumber,
      confirmations: receipt.confirmations,
    };
  }

  /**
   * Subscribe to on-chain events with real-time WebSocket updates.
   * @param contractAddress Address of the contract to monitor
   * @param abi Contract ABI containing event definitions
   * @param eventName Name of the event to subscribe to
   * @param callback Function called when event is received with decoded log
   * @param filter Optional indexed parameter filters (e.g., { sender: "0x..." })
   * @returns EventSubscription with unsubscribe method
   */
  subscribeToEvents(
    contractAddress: string,
    abi: any[],
    eventName: string,
    callback: (log: any) => void,
    filter?: Record<string, unknown>
  ): EventSubscription {
    const subId = `${contractAddress}:${eventName}:${Date.now()}`;
    
    // Store subscription for reconnection
    this._subscriptions.set(subId, {
      contract: new ethers.Contract(contractAddress, abi, this.provider),
      eventName,
      callback,
      filter,
    });

    // Initialize WebSocket connection if not already connected
    this._ensureWsConnection();

    // Set up listener on WS provider
    this._attachListener(subId);

    return {
      unsubscribe: () => {
        this._subscriptions.delete(subId);
        if (this._wsProvider) {
          this._wsProvider.removeAllListeners(eventName);
        }
      },
    };
  }

  private _ensureWsConnection(): void {
    if (this._wsProvider && !this._wsProvider.websocket.closed) {
      return;
    }

    // Convert HTTP RPC URL to WebSocket URL
    const wsUrl = this.config.rpcUrl.replace(/^http/, "ws");
    this._wsProvider = new ethers.WebSocketProvider(wsUrl);

    this._wsProvider.websocket.on("close", () => {
      this._handleDisconnect();
    });

    this._wsProvider.websocket.on("error", () => {
      this._handleDisconnect();
    });

    this._reconnectAttempts = 0;
  }

  private _handleDisconnect(): void {
    if (this._reconnectAttempts >= this._maxReconnectAttempts) {
      console.error(`WebSocket reconnection failed after ${this._maxReconnectAttempts} attempts`);
      return;
    }

    this._reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts), 30000);

    setTimeout(() => {
      this._ensureWsConnection();
      // Resubscribe all active subscriptions
      for (const subId of this._subscriptions.keys()) {
        this._attachListener(subId);
      }
    }, delay);
  }

  private _attachListener(subId: string): void {
    const sub = this._subscriptions.get(subId);
    if (!sub || !this._wsProvider) return;

    const wsContract = new ethers.Contract(
      sub.contract.target as string,
      sub.contract.interface.fragments,
      this._wsProvider
    );

    const listener = (...args: any[]) => {
      // Last arg is the EventLog object
      const eventLog = args[args.length - 1];
      
      // Apply indexed parameter filters
      if (sub.filter) {
        for (const [key, value] of Object.entries(sub.filter)) {
          if (eventLog.args[key] !== undefined && 
              eventLog.args[key].toString().toLowerCase() !== String(value).toLowerCase()) {
            return; // Skip non-matching events
          }
        }
      }

      // Decode and normalize the event data
      const decoded = {
        name: eventLog.fragment?.name || sub.eventName,
        args: Object.fromEntries(
          eventLog.fragment?.inputs?.map((input: any, i: number) => [
            input.name || `arg${i}`,
            eventLog.args[i],
          ]) || []
        ),
        blockNumber: eventLog.blockNumber,
        transactionHash: eventLog.transactionHash,
        logIndex: eventLog.index,
      };

      sub.callback(decoded);
    };

    wsContract.on(sub.eventName, listener);
  }

  async getOpenTasks(options?: {
    offset?: number;
    limit?: number;
    status?: number;
  }): Promise<any[]> {
    const offset = options?.offset ?? 0;
    const limit = options?.limit ?? 50;
    const statusFilter = options?.status ?? 0;

    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );

    const currentBlock = await this.provider.getBlockNumber();
    let count: bigint;

    if (this._taskCountCache && this._taskCountCache.blockNumber === currentBlock) {
      count = BigInt(this._taskCountCache.value);
    } else {
      count = await router.taskCount();
      this._taskCountCache = { value: Number(count), blockNumber: currentBlock };
    }

    const end = Math.min(offset + limit, Number(count));
    if (offset >= Number(count)) return [];

    const openTasks = [];
    const batchSize = 10;

    for (let i = offset; i < end; i += batchSize) {
      const batchEnd = Math.min(i + batchSize, end);
      const promises = [];
      for (let j = i; j < batchEnd; j++) {
        promises.push(router.tasks(j).then((t: any) => ({ id: j, data: t })));
      }

      const results = await Promise.all(promises);
      for (const result of results) {
        const task = result.data;
        if (task[5] === statusFilter) {
          openTasks.push({
            id: result.id,
            creator: task[0],
            description: task[2],
            reward: task[3],
            deadline: task[4],
            status: task[5],
          });
        }
      }
    }

    return openTasks;
  }
}
