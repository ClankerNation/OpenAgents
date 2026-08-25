/**
 * @contributor-info rafaio1
 * @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.
 * @env os=linux arch=x64 home=/root working_dir=/tmp/openagents_issue_202 shell=/bin/bash
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

  // --- Event Subscription & Decoding (Issue #196) ---
  private _wsProvider: ethers.WebSocketProvider | null = null;
  private _activeSubscriptions: Map<string, { contract: ethers.Contract; eventName: string; callback: (...args: any[]) => void; filter?: Record<string, unknown> }> = new Map();
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  /**
   * Subscribe to real-time contract events via WebSocket.
   * Auto-reconnects on drop and resubscribes all active listeners.
   * @param contractAddress Address of the contract to monitor
   * @param abi Contract ABI (human-readable or JSON)
   * @param eventName Name of the event to listen for
   * @param callback Function called with decoded event args on each emission
   * @param filter Optional indexed parameter filters (e.g., { sender: "0x..." })
   * @returns Subscription ID for later unsubscription
   */
  subscribeToEvents(
    contractAddress: string,
    abi: ethers.InterfaceAbi,
    eventName: string,
    callback: (...args: any[]) => void,
    filter?: Record<string, unknown>
  ): string {
    const subId = `${contractAddress}:${eventName}:${Date.now()}`;
    this._activeSubscriptions.set(subId, {
      contract: new ethers.Contract(contractAddress, abi, this.provider),
      eventName,
      callback,
      filter,
    });
    this._ensureWsConnected();
    return subId;
  }

  /**
   * Unsubscribe from a previously registered event listener.
   * @param subId Subscription ID returned by subscribeToEvents
   */
  unsubscribeFromEvents(subId: string): void {
    this._activeSubscriptions.delete(subId);
  }

  private _ensureWsConnected(): void {
    if (this._wsProvider && !this._wsProvider.websocket.closed) return;

    const wsUrl = this.config.rpcUrl.replace(/^http/, "ws");
    this._wsProvider = new ethers.WebSocketProvider(wsUrl);

    this._wsProvider.websocket.on("open", () => {
      this._resubscribeAll();
    });

    this._wsProvider.websocket.on("close", () => {
      if (!this._reconnectTimer) {
        this._reconnectTimer = setTimeout(() => {
          this._reconnectTimer = null;
          this._ensureWsConnected();
        }, 3000);
      }
    });

    this._wsProvider.websocket.on("error", () => {
      // Error triggers close, which triggers reconnect
    });
  }

  private _resubscribeAll(): void {
    if (!this._wsProvider) return;
    for (const [subId, sub] of this._activeSubscriptions.entries()) {
      try {
        const wsContract = new ethers.Contract(
          sub.contract.target as string,
          sub.contract.interface,
          this._wsProvider
        );
        const filterArgs = sub.filter ? Object.values(sub.filter) : [];
        const eventFilter = wsContract.filters[sub.eventName]?.(...filterArgs);
        if (eventFilter) {
          wsContract.on(eventFilter, (...args: any[]) => {
            sub.callback(...args);
          });
        } else {
          wsContract.on(sub.eventName, (...args: any[]) => {
            sub.callback(...args);
          });
        }
      } catch {
        // Skip failed subscriptions silently; will retry on next reconnect
      }
    }
  }

  /**
   * Decode raw event log data using contract ABI.
   * @param contractAddress Address of the emitting contract
   * @param abi Contract ABI
   * @param log Raw log object from transaction receipt or provider
   * @returns Decoded event with name and typed arguments, or null if unrecognized
   */
  decodeEventLog(
    contractAddress: string,
    abi: ethers.InterfaceAbi,
    log: { topics: string[]; data: string }
  ): { name: string; args: Record<string, unknown> } | null {
    try {
      const iface = new ethers.Interface(abi);
      const parsed = iface.parseLog({ topics: log.topics, data: log.data });
      if (!parsed) return null;
      const args: Record<string, unknown> = {};
      parsed.fragment.inputs.forEach((input, i) => {
        args[input.name || `arg${i}`] = parsed.args[i];
      });
      return { name: parsed.name, args };
    } catch {
      return null;
    }
  }
}
