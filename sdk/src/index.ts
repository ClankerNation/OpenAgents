// @contributor-info rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

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
   * Deploy a contract and wait for confirmation.
   */
  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: string,
    args: unknown[] = [],
    confirmations: number = 1
  ): Promise<DeploymentReceipt> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);

    const receipt = await contract.deploymentTransaction()?.wait(confirmations);

    if (!receipt || !contract.target) {
      throw new Error("Contract deployment failed: no receipt or address");
    }

    return {
      address: contract.target as string,
      txHash: receipt.hash,
      gasUsed: receipt.gasUsed,
      blockNumber: receipt.blockNumber,
      confirmations: receipt.confirmations ?? confirmations,
    };
  }

  /**
   * Subscribe to on-chain events with auto-reconnect and indexed filtering.
   * @param contractAddress Address of the contract to monitor
   * @param abi Contract ABI (human-readable or JSON)
   * @param eventName Name of the event to subscribe to
   * @param callback Function called with decoded event log on each emission
   * @param filters Optional indexed parameter filters (e.g., { sender: "0x..." })
   * @returns Subscription handle with unsubscribe method
   */
  subscribeToEvents(
    contractAddress: string,
    abi: ethers.InterfaceAbi,
    eventName: string,
    callback: (log: ethers.LogDescription) => void,
    filters?: Record<string, unknown>
  ): EventSubscription {
    const iface = new ethers.Interface(abi as string[]);
    const eventFragment = iface.getEvent(eventName);
    if (!eventFragment) {
      throw new Error(`Event "${eventName}" not found in ABI`);
    }

    // Build filter topics array for indexed parameters
    const topics: (string | string[] | null)[] = [iface.getEventTopic(eventFragment)];
    if (filters && eventFragment.inputs) {
      let topicIndex = 1;
      for (const param of eventFragment.inputs) {
        if (param.indexed) {
          const val = filters[param.name];
          if (val !== undefined) {
            if (Array.isArray(val)) {
              topics[topicIndex] = val.map((v) =>
                typeof v === "string" && v.startsWith("0x")
                  ? ethers.zeroPadValue(v, 32)
                  : ethers.zeroPadValue(ethers.toBeHex(v), 32)
              );
            } else {
              topics[topicIndex] =
                typeof val === "string" && val.startsWith("0x")
                  ? ethers.zeroPadValue(val, 32)
                  : ethers.zeroPadValue(ethers.toBeHex(val), 32);
            }
          }
          topicIndex++;
        }
      }
    }

    let active = true;
    let wsProvider: ethers.WebSocketProvider | null = null;

    const connect = () => {
      if (!active) return;

      try {
        // Convert HTTP URL to WS URL for WebSocket provider
        const wsUrl = this.config.rpcUrl
          .replace(/^http/, "ws")
          .replace(/^https/, "wss");
        wsProvider = new ethers.WebSocketProvider(wsUrl);

        wsProvider.websocket.on("open", () => {
          if (!active) return;
          wsProvider!.on(
            { address: contractAddress, topics: topics as string[] },
            (rawLog: ethers.Log) => {
              try {
                const parsed = iface.parseLog({
                  topics: rawLog.topics as string[],
                  data: rawLog.data,
                });
                if (parsed) {
                  callback(parsed);
                }
              } catch {
                // Skip logs that don't match the expected event signature
              }
            }
          );
        });

        wsProvider.websocket.on("close", () => {
          if (active) {
            // Auto-reconnect after 2 seconds
            setTimeout(connect, 2000);
          }
        });

        wsProvider.websocket.on("error", () => {
          // Error handler — reconnect handled by close event
        });
      } catch {
        if (active) {
          setTimeout(connect, 2000);
        }
      }
    };

    connect();

    return {
      unsubscribe: () => {
        active = false;
        if (wsProvider) {
          wsProvider.removeAllListeners();
          wsProvider.destroy();
          wsProvider = null;
        }
      },
    };
  }
}
