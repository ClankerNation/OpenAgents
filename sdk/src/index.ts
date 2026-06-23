import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface DeploymentResult {
  registryAddress: string;
  routerAddress: string;
  registry: ethers.Contract;
  router: ethers.Contract;
  deployTxHash: string;
  routerTxHash: string;
}

export interface DeployerConfig {
  privateKey: string;
  rpcUrl: string;
  registryFee?: bigint;
  platformFee?: number;
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
}

export async function deployContracts(config: DeployerConfig): Promise<DeploymentResult> {
  const provider = new ethers.JsonRpcProvider(config.rpcUrl);
  const signer = new ethers.Wallet(config.privateKey, provider);

  const registryFee = config.registryFee ?? ethers.parseEther("0.01");
  const platformFee = config.platformFee ?? 250;

  const registryFactory = new ethers.ContractFactory(
    [
      "constructor(uint256 _registrationFee)",
      "function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32)",
      "function registrationFee() view returns (uint256)",
      "function owner() view returns (address)",
      "function getAgent(bytes32 agentId) view returns (address owner,string name,string endpoint,uint256 reputation,uint256 tasksCompleted,uint256 registeredAt,bool active)",
    ],
    "0x" +
      // Minimal bytecode placeholder — in production this comes from compiled artifacts.
      // The helper deploys via the full artifact when available.
      "608060405234801561001057600080fd5b5060df8061001f6000396000f3fe",
    signer
  );

  const registry = await registryFactory.deploy(registryFee);
  await registry.waitForDeployment();
  const registryAddress = await registry.getAddress();

  const routerFactory = new ethers.ContractFactory(
    [
      "constructor(address _registry, uint256 _platformFee)",
      "function createTask(string calldata description, uint256 deadline) external payable returns (uint256)",
      "function assignTask(uint256 taskId, bytes32 agentId)",
      "function completeTask(uint256 taskId, bytes calldata result)",
      "function taskCount() view returns (uint256)",
      "function platformFee() view returns (uint256)",
    ],
    "0x" +
      "6080604052348015600f57600080fd5b50603f80601d6000396000f3fe",
    signer
  );

  const router = await routerFactory.deploy(registryAddress, platformFee);
  await router.waitForDeployment();
  const routerAddress = await router.getAddress();

  return {
    registryAddress,
    routerAddress,
    registry,
    router,
    deployTxHash: registry.deploymentTransaction()?.hash ?? "",
    routerTxHash: router.deploymentTransaction()?.hash ?? "",
  };
}

export async function deployWithArtifacts(
  config: DeployerConfig & { artifactsDir: string }
): Promise<DeploymentResult> {
  const { artifactsDir, ...deployConfig } = config;

  const registryArtifact = await import(
    `${artifactsDir}/AgentRegistry.json`
  );
  const routerArtifact = await import(`${artifactsDir}/TaskRouter.json`);

  const provider = new ethers.JsonRpcProvider(deployConfig.rpcUrl);
  const signer = new ethers.Wallet(deployConfig.privateKey, provider);

  const registryFee = deployConfig.registryFee ?? ethers.parseEther("0.01");
  const platformFee = deployConfig.platformFee ?? 250;

  const registryFactory = new ethers.ContractFactory(
    registryArtifact.abi,
    registryArtifact.bytecode,
    signer
  );

  const registry = await registryFactory.deploy(registryFee);
  await registry.waitForDeployment();
  const registryAddress = await registry.getAddress();

  const routerFactory = new ethers.ContractFactory(
    routerArtifact.abi,
    routerArtifact.bytecode,
    signer
  );

  const router = await routerFactory.deploy(registryAddress, platformFee);
  await router.waitForDeployment();
  const routerAddress = await router.getAddress();

  return {
    registryAddress,
    routerAddress,
    registry,
    router,
    deployTxHash: registry.deploymentTransaction()?.hash ?? "",
    routerTxHash: router.deploymentTransaction()?.hash ?? "",
  };
}
