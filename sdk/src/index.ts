/**
 * @contributor doubao-agent (spiritwanghs fork)
 * @platform-config Autonomous coding agent executing GitHub bounties; user asked to do all available bounty issues.
 * @env os=linux arch=x64 home_dir=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=bash
 * @timestamp 2026-09-29T03:20:00Z
 */
import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
  /** Optional WebSocket URL for real-time events. Defaults to rpcUrl with https->wss. */
  wsUrl?: string;
}

export type EventCallback<T = Record<string, any>> = (
  decoded: T,
  payload: ethers.ContractEventPayload
) => void;

function toWsUrl(rpcUrl: string): string {
  if (rpcUrl.startsWith("ws://") || rpcUrl.startsWith("wss://")) return rpcUrl;
  return rpcUrl.replace(/^https:\/\//, "wss://").replace(/^http:\/\//, "ws://");
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

  /**
   * Subscribe to on-chain contract events in real time.
   * Uses a WebSocket provider (ethers auto-reconnects and resubscribes).
   * Logs are decoded with parameter names and values; optional filtering by
   * indexed parameter values is applied before the callback fires.
   *
   * @returns an unsubscribe function.
   */
  async subscribeToEvents<T = Record<string, any>>(
    contractAddress: string,
    abi: any[],
    eventName: string,
    callback: EventCallback<T>,
    filter: Record<string, any> = {}
  ): Promise<() => void> {
    const wsUrl = this.config.wsUrl ?? toWsUrl(this.config.rpcUrl);
    const wsProvider = new ethers.WebSocketProvider(wsUrl);
    const contract = new ethers.Contract(contractAddress, abi, wsProvider);

    // Resolve the event fragment to validate the name and get inputs.
    const iface = contract.interface;
    const fragment = iface.getEvent(eventName);
    if (!fragment) throw new Error(`Unknown event: ${eventName}`);

    const handler = (...args: any[]) => {
      const payload = args[args.length - 1] as ethers.ContractEventPayload;
      const decoded: Record<string, any> = {};
      const inputs = fragment.inputs;
      for (let i = 0; i < inputs.length; i++) {
        const name = inputs[i].name || `arg${i}`;
        decoded[name] = args[i];
      }
      if (this.matchesFilter(decoded, filter, fragment.inputs)) {
        callback(decoded as T, payload);
      }
    };

    contract.on(fragment, handler);

    return async () => {
      contract.off(fragment, handler);
      await wsProvider.destroy();
    };
  }

  private matchesFilter(
    decoded: Record<string, any>,
    filter: Record<string, any>,
    inputs: readonly ethers.ParamType[]
  ): boolean {
    for (const key of Object.keys(filter)) {
      if (!(key in decoded)) return false;
      if (decoded[key] !== filter[key]) return false;
    }
    return true;
  }
}
