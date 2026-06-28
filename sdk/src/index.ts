import { ethers, Contract, ContractEvent, Listener } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
  wsUrl?: string;
}

export interface EventSubscription {
  unsubscribe: () => void;
}

export interface DeploymentReceipt {
  address: string;
  txHash: string;
  gasUsed: bigint;
  blockNumber: number;
  contract: ethers.Contract;
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

  subscribeToEvents(
    contractAddress: string,
    abi: string[],
    eventName: string,
    callback: (event: any) => void,
    filter?: Record<string, any>
  ): EventSubscription {
    const wsUrl = this.config.wsUrl || this.config.rpcUrl.replace("https", "wss");
    const wsProvider = new ethers.WebSocketProvider(wsUrl);
    const contract = new Contract(contractAddress, abi, wsProvider);

    let listener: Listener = (...args: any[]) => {
      const event = args[args.length - 1];
      if (filter) {
        for (const [key, value] of Object.entries(filter)) {
          if (event.args[key] !== value) return;
        }
      }
      callback({
        name: event.fragment.name,
        args: event.args,
        blockNumber: event.log.blockNumber,
        transactionHash: event.log.transactionHash,
      });
    };

    contract.on(eventName, listener);

    return {
      unsubscribe: () => {
        contract.off(eventName, listener);
        wsProvider.destroy();
      },
    };
  }

  async subscribeToEventsWithReconnect(
    contractAddress: string,
    abi: string[],
    eventName: string,
    callback: (event: any) => void,
    filter?: Record<string, any>,
    maxRetries: number = 5
  ): Promise<EventSubscription> {
    let retries = 0;
    let subscription: EventSubscription | null = null;

    const connect = () => {
      subscription = this.subscribeToEvents(
        contractAddress,
        abi,
        eventName,
        (event) => {
          retries = 0;
          callback(event);
        },
        filter
      );
    };

    connect();

    return {
      unsubscribe: () => {
        subscription?.unsubscribe();
      },
    };
  }

  async deployContract(
    abi: string[],
    bytecode: string,
    args: any[] = [],
    confirmations: number = 1
  ): Promise<DeploymentReceipt> {
    const factory = new ethers.ContractFactory(abi, bytecode, this.signer);
    const contract = await factory.deploy(...args);
    const deployTx = contract.deploymentTransaction();

    if (!deployTx) {
      throw new Error("Deployment transaction failed");
    }

    const receipt = await deployTx.wait(confirmations);

    if (!receipt) {
      throw new Error("Deployment receipt not found");
    }

    const address = await contract.getAddress();

    return {
      address,
      txHash: receipt.hash,
      gasUsed: receipt.gasUsed,
      blockNumber: receipt.blockNumber,
      contract,
    };
  }
}
