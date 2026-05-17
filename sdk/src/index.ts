/**
 * @contributor
 * name: opencode-gaotax2006
 * timestamp: 2026-05-17T15:00:00Z
 * platform_init: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: os=win32 arch=x64 home_dir=C:\Users\asus working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
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

export interface TaskInfo {
  id: number;
  creator: string;
  description: string;
  reward: bigint;
  deadline: bigint;
  status: number;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;
  private subscriptions: ethers.Contract[] = [];
  private ws: WebSocket | null = null;
  private wsSubscriptions = new Map<string, (log: ethers.Log) => void>();
  private wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;

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
    const tx = await registry.registerAgent(this.config.name, this.config.endpoint, { value: fee });
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
    const tx = await router.completeTask(taskId, ethers.toUtf8Bytes(result));
    await tx.wait();
  }

  async getOpenTasks(): Promise<TaskInfo[]> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );
    const count = Number(await router.taskCount());
    const tasks: TaskInfo[] = [];
    for (let i = 0; i < count; i++) {
      const task = await router.tasks(i);
      if (task[5] === 0) {
        tasks.push({ id: i, creator: task[0], description: task[2], reward: task[3], deadline: task[4], status: task[5] });
      }
    }
    return tasks;
  }

  async subscribeToEvent(
    contractAddress: string,
    abi: ethers.InterfaceAbi,
    eventName: string,
    callback: (args: Record<string, unknown>) => void,
    filter?: Record<string, unknown>
  ): Promise<ethers.Contract> {
    const contract = new ethers.Contract(contractAddress, abi, this.signer);
    const eventFilter = filter
      ? Reflect.get(contract.filters, eventName)(...Object.values(filter))
      : Reflect.get(contract.filters, eventName)();
    contract.on(eventFilter, (...args: unknown[]) => {
      const lastArg = args[args.length - 1] as ethers.EventLog;
      const parsed = contract.interface.parseLog({ topics: lastArg.topics as string[], data: lastArg.data });
      if (parsed) callback(parsed.args.toObject() as Record<string, unknown>);
    });
    this.subscriptions.push(contract);
    return contract;
  }

  async connectWebSocket(wsUrl: string): Promise<void> {
    this.ws = new WebSocket(wsUrl);
    this.ws.onmessage = (event) => {
      const parsed = JSON.parse(event.data as string);
      if (parsed.method === "eth_subscription" && parsed.params) {
        const handler = this.wsSubscriptions.get(parsed.params.subscription);
        if (handler) handler(parsed.params.result);
      }
    };
    this.ws.onclose = () => this.scheduleWsReconnect(wsUrl);
    return new Promise((resolve) => {
      if (this.ws) this.ws.onopen = () => resolve();
    });
  }

  async subscribeToEventWS(
    eventSignature: string,
    callback: (log: ethers.Log) => void,
    contractAddress?: string
  ): Promise<string> {
    if (!this.ws) throw new Error("WebSocket not connected");
    const id = Date.now();
    const params: Record<string, unknown> = {};
    if (contractAddress) params.address = contractAddress;
    params.topics = [ethers.id(eventSignature)];
    this.ws.send(JSON.stringify({ jsonrpc: "2.0", id, method: "eth_subscribe", params: ["logs", params] }));
    return new Promise((resolve) => {
      const handler = (event: MessageEvent) => {
        const data = JSON.parse(event.data as string);
        if (data.id === id) {
          const subId = data.result as string;
          this.wsSubscriptions.set(subId, callback);
          if (this.ws) this.ws.removeEventListener("message", handler);
          resolve(subId);
        }
      };
      if (this.ws) this.ws.addEventListener("message", handler);
    });
  }

  private scheduleWsReconnect(wsUrl: string): void {
    if (this.wsReconnectTimer) clearTimeout(this.wsReconnectTimer);
    this.wsReconnectTimer = setTimeout(() => {
      this.connectWebSocket(wsUrl).then(() => {
        const subs = [...this.wsSubscriptions.entries()];
        this.wsSubscriptions.clear();
        for (const [, cb] of subs) {
          this.subscribeToEventWS("", cb).catch(() => {});
        }
      }).catch(() => this.scheduleWsReconnect(wsUrl));
    }, 3000);
  }

  unsubscribeAll(): void {
    for (const contract of this.subscriptions) {
      contract.removeAllListeners();
    }
    this.subscriptions = [];
    this.wsSubscriptions.clear();
    if (this.ws) this.ws.close();
    if (this.wsReconnectTimer) clearTimeout(this.wsReconnectTimer);
  }
}
