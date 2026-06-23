import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

/**
 * Result of a pre-signed deployment — deploys via CREATE2 for deterministic addresses.
 */
export interface PreDeployResult {
  predictedAddress: string;
  transactionHash: string;
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

  /**
   * Deploy a contract deterministically using CREATE2 (pre-audit deployment helper).
   * Predicts address before deployment, then deploys and returns the contract instance.
   */
  async deployContractPreSigned(
    abi: any[],
    bytecode: string,
    args: any[] = [],
    salt: string = ""
  ): Promise<PreDeployResult> {
    // Predict CREATE2 address
    const deployerAddress = this.signer.address;
    const hash = ethers.keccak256(
      ethers.solidityPacked(["bytes1", "address", "bytes32", "bytes32"], [
        "0xff",
        deployerAddress,
        ethers.keccak256(salt),
        ethers.keccak256(bytecode + (args.length ? ethers.AbiCoder.defaultAbiCoder().encode(args.map((_, i) => "uint256"), args).replace("0x", "") : "")),
      ])
    );
    const predictedAddress = ethers.getCreate2Address(deployerAddress, ethers.keccak256(salt || "0x"), hash);

    // Deploy
    const factory = new ethers.ContractFactory(abi, bytecode + (args.length ? ethers.AbiCoder.defaultAbiCoder().encode(args.map((_, i) => "uint256"), args).replace("0x", "") : ""), this.signer);
    const deploymentTx = await factory.deploy(...args, { salt: ethers.hexlify(ethers.keccak256(salt || "0x")) });
    const receipt = await deploymentTx.waitForDeployment();
    const actualAddress = await receipt.getAddress();

    return {
      predictedAddress,
      transactionHash: receipt.hash,
      blockNumber: receipt.blockNumber ?? 0,
      contract: factory.attach(actualAddress),
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
}
