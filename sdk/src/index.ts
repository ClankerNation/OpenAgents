import { ethers } from "ethers";

// @fix-author rafaio1
// @date 2026-08-25T00:00:00Z
// @runtime linux x64 /tmp/openagents_issue_196 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface DeployResult {
  address: string;
  txHash: string;
  blockNumber: number;
  gasUsed: bigint;
}

export interface DeploymentOptions {
  overrides?: ethers.Overrides;
  confirmations?: number;
}

export interface DecodedEvent {
  name: string;
  args: Record<string, unknown>;
  log: ethers.Log;
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
   * Subscribe to contract events with automatic decoding
   * @param address Contract address to monitor
   * @param abi Contract ABI containing event definitions
   * @param eventName Specific event name to filter, or undefined for all events
   * @param callback Handler invoked for each decoded event
   * @returns Unsubscribe function to stop listening
   */
  subscribeToEvents(
    address: string,
    abi: ethers.InterfaceAbi,
    eventName: string | undefined,
    callback: (event: DecodedEvent) => void
  ): () => void {
    const contract = new ethers.Contract(address, abi, this.provider);
    const iface = new ethers.Interface(abi);

    const handler = (log: ethers.Log) => {
      try {
        const parsed = iface.parseLog({ topics: log.topics as string[], data: log.data });
        if (!parsed) return;
        if (eventName && parsed.name !== eventName) return;

        const args: Record<string, unknown> = {};
        parsed.fragment.inputs.forEach((input, idx) => {
          args[input.name || `arg${idx}`] = parsed.args[idx];
        });

        callback({ name: parsed.name, args, log });
      } catch {
        // Skip logs that don't match any known event in the ABI
      }
    };

    const filter = eventName ? contract.filters[eventName]() : "*";
    contract.on(filter, handler);

    return () => {
      contract.off(filter, handler);
    };
  }

  /**
   * Decode raw event logs using a contract ABI
   * @param abi Contract ABI with event definitions
   * @param logs Raw logs to decode
   * @returns Array of decoded events (unrecognized logs are filtered out)
   */
  decodeEventLogs(abi: ethers.InterfaceAbi, logs: ethers.Log[]): DecodedEvent[] {
    const iface = new ethers.Interface(abi);
    const decoded: DecodedEvent[] = [];

    for (const log of logs) {
      try {
        const parsed = iface.parseLog({ topics: log.topics as string[], data: log.data });
        if (!parsed) continue;

        const args: Record<string, unknown> = {};
        parsed.fragment.inputs.forEach((input, idx) => {
          args[input.name || `arg${idx}`] = parsed.args[idx];
        });

        decoded.push({ name: parsed.name, args, log });
      } catch {
        // Skip unrecognized logs
      }
    }

    return decoded;
  }

  async deployContract(
    abi: ethers.InterfaceAbi,
    bytecode: string,
    args: unknown[] = [],
    options: DeploymentOptions = {}
  ): Promise<DeployResult> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args, { ...options.overrides });
    const receipt = await contract.deploymentTransaction()?.wait(options.confirmations ?? 1);

    if (!receipt || !contract.target) {
      throw new Error("Deployment failed: no receipt or contract address");
    }

    return {
      address: contract.target as string,
      txHash: receipt.hash,
      blockNumber: receipt.blockNumber,
      gasUsed: receipt.gasUsed,
    };
  }

  getContract(address: string, abi: ethers.InterfaceAbi, useSigner: boolean = false): ethers.Contract {
    return new ethers.Contract(address, abi, useSigner ? this.signer : this.provider);
  }

  async isContractDeployed(address: string): Promise<boolean> {
    const code = await this.provider.getCode(address);
    return code !== "0x" && code.length > 2;
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
    const tx = await router.completeTask(taskId, ethers.toUtf8Bytes(result));
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
        openTasks.push({ id: i, creator: task[0], description: task[2], reward: task[3], deadline: task[4] });
      }
    }
    return openTasks;
  }
}
