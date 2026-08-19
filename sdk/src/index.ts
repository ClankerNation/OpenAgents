/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
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

  /**
   * Subscribe to contract events via WebSocket with auto-reconnect.
   * @param contractAddress Address of the contract
   * @param abi Contract ABI
   * @param eventName Name of the event to listen for
   * @param callback Function to call when event is received
   * @param filters Optional indexed parameter filters
   */
  subscribeToEvents(
    contractAddress: string,
    abi: ethers.InterfaceAbi,
    eventName: string,
    callback: (event: any) => void,
    filters?: Record<string, any>
  ): void {
    const wsUrl = this.config.rpcUrl.replace(/^http/, "ws");
    let wsProvider = new ethers.WebSocketProvider(wsUrl);
    
    const attachListener = (provider: ethers.WebSocketProvider) => {
      const contract = new ethers.Contract(contractAddress, abi, provider);
      
      contract.on(eventName, (...args: any[]) => {
        const event = args[args.length - 1];
        let matchesFilter = true;
        if (filters) {
          for (const [key, value] of Object.entries(filters)) {
            if (event.args && event.args[key] !== value) {
              matchesFilter = false;
              break;
            }
          }
        }
        if (matchesFilter) {
          callback(event);
        }
      });
      
      provider.websocket.on("close", () => {
        setTimeout(() => {
          try {
            const newProvider = new ethers.WebSocketProvider(wsUrl);
            attachListener(newProvider);
          } catch (e) {
            // Reconnect failed
          }
        }, 5000);
      });
    };
    
    attachListener(wsProvider);
  }

}
