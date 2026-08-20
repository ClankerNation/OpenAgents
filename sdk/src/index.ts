// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
import { ethers } from "ethers";

export interface EventSubscription {
  unsubscribe: () => void;
}

export interface EventFilter {
  [key: string]: any;
}


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

  /**
   * Subscribe to contract events with automatic decoding and reconnection.
   * @param contractAddress The contract to listen to
   * @param eventName The event name to filter
   * @param callback Handler receiving decoded event data
   * @param filter Optional indexed parameter filters
   * @returns Subscription handle with unsubscribe method
   */
  subscribeToEvents(
    contractAddress: string,
    eventName: string,
    callback: (event: any) => void,
    filter?: EventFilter
  ): EventSubscription {
    let wsProvider: ethers.WebSocketProvider | null = null;
    let contract: ethers.Contract | null = null;
    let active = true;

    const connect = () => {
      if (!active) return;

      try {
        // Convert HTTP RPC URL to WebSocket
        const wsUrl = this.config.rpcUrl
          .replace(/^http/, "ws")
          .replace(/^https/, "wss");
        
        wsProvider = new ethers.WebSocketProvider(wsUrl);
        
        wsProvider.websocket.on("close", () => {
          if (active) {
            setTimeout(connect, 3000); // Auto-reconnect after 3s
          }
        });

        wsProvider.websocket.on("error", () => {
          // Error triggers close, which triggers reconnect
        });

        contract = new ethers.Contract(contractAddress, [], wsProvider);
        
        const applyFilter = filter ? [eventName, filter] : [eventName];
        
        contract.on(...applyFilter, (...args: any[]) => {
          // Last arg is the log object; preceding args are decoded params
          const log = args[args.length - 1];
          const decoded: Record<string, any> = {};
          
          // Map positional args to named parameters if fragment available
          if (log.fragment?.inputs) {
            log.fragment.inputs.forEach((input: any, idx: number) => {
              decoded[input.name || `param${idx}`] = args[idx];
            });
          } else {
            // Fallback: pass raw args
            decoded.args = args.slice(0, -1);
          }
          
          decoded.blockNumber = log.blockNumber;
          decoded.transactionHash = log.hash;
          decoded.logIndex = log.index;
          
          callback(decoded);
        });
      } catch (err) {
        if (active) {
          setTimeout(connect, 5000);
        }
      }
    };

    connect();

    return {
      unsubscribe: () => {
        active = false;
        if (contract) {
          contract.removeAllListeners(eventName);
        }
        if (wsProvider) {
          wsProvider.destroy();
        }
      },
    };
  }
}
