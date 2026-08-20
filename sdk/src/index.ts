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
  contract: ethers.Contract;
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

  /**
   * Subscribe to contract events with auto-reconnect and indexed parameter filtering.
   * @param contractAddress Address of the contract to monitor
   * @param abi Contract ABI (must include event definitions)
   * @param eventName Name of the event to subscribe to
   * @param callback Function called with decoded event arguments
   * @param filters Optional indexed parameter filters (e.g., { sender: "0x..." })
   * @returns EventSubscription handle with unsubscribe method
   */
  subscribeToEvents(
    contractAddress: string,
    abi: ethers.InterfaceAbi,
    eventName: string,
    callback: (...args: any[]) => void,
    filters?: Record<string, any>
  ): EventSubscription {
    const contract = new ethers.Contract(contractAddress, abi, this.provider);
    let active = true;

    const startListener = () => {
      if (!active) return;

      // Build filter from indexed parameters if provided
      let eventFilter: ethers.EventFilter | undefined;
      if (filters) {
        try {
          eventFilter = contract.filters[eventName](...Object.values(filters));
        } catch {
          // Fallback: use unfiltered listener if filter construction fails
          eventFilter = undefined;
        }
      }

      const handler = (...args: any[]) => {
        if (!active) return;
        // Last arg is always the Log object; preceding args are decoded params
        callback(...args);
      };

      if (eventFilter) {
        contract.on(eventFilter, handler);
      } else {
        contract.on(eventName, handler);
      }

      // Auto-reconnect on WebSocket drop
      const wsProvider = this.provider as any;
      if (wsProvider.websocket || wsProvider._websocket) {
        const ws = wsProvider.websocket || wsProvider._websocket;
        const reconnectHandler = () => {
          if (!active) return;
          // Re-subscribe after reconnection
          setTimeout(() => {
            if (active) {
              contract.off(eventFilter || eventName, handler);
              startListener();
            }
          }, 1000);
        };
        ws.on?.("close", reconnectHandler);
        ws.on?.("error", reconnectHandler);
      }
    };

    startListener();

    return {
      unsubscribe: () => {
        active = false;
        contract.removeAllListeners(eventName);
      },
    };
  }

  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: string,
    args: any[] = [],
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
      contract: new ethers.Contract(contract.target, abi, this.signer),
    };
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
    return receipt!.logs[0].topics[1];
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
