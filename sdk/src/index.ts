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
}

/**
 * Contract deployment helper for the OpenAgents SDK.
 * Provides deployContract() and deployWithArtifacts() utilities.
 */
export interface DeploymentReceipt {
  contractAddress: string;
  transactionHash: string;
  blockNumber: number;
  gasUsed: bigint;
  deployer: string;
  abi: unknown[];
  bytecode: string;
}

export interface DeployOptions {
  /** Constructor arguments for the contract */
  constructorArgs?: unknown[];
  /** Override gas limit */
  gasLimit?: number;
  /** Override nonce */
  nonce?: number;
}

/**
 * Deploy a contract using raw ABI and bytecode.
 * @param signer ethers Signer to deploy with
 * @param abi Contract ABI array
 * @param bytecode Contract bytecode (0x-prefixed hex string)
 * @param options Optional deployment parameters
 * @returns DeploymentReceipt with contract address and tx details
 */
export async function deployContract(
  signer: ethers.Signer,
  abi: unknown[],
  bytecode: string,
  options: DeployOptions = {}
): Promise<DeploymentReceipt> {
  const { constructorArgs = [], gasLimit, nonce } = options;

  const factory = new ethers.ContractFactory(abi, bytecode, signer);

  const deploymentTx = nonce !== undefined
    ? await factory.deploy(...constructorArgs, { nonce, gasLimit })
    : await factory.deploy(...constructorArgs, { gasLimit });

  const receipt = await deploymentTx.deploymentTransaction()?.wait();

  if (!receipt) {
    throw new Error("Contract deployment transaction was not confirmed");
  }

  return {
    contractAddress: deploymentTx.target as string,
    transactionHash: deploymentTx.hash,
    blockNumber: receipt.blockNumber,
    gasUsed: receipt.gasUsed,
    deployer: await signer.getAddress(),
    abi,
    bytecode,
  };
}

/**
 * Deploy a contract using Hardhat artifacts (ABI + bytecode from compilation).
 * @param signer ethers Signer to deploy with
 * @param artifact Hardhat-style artifact object with abi and bytecode
 * @param options Optional deployment parameters
 * @returns DeploymentReceipt with contract address and tx details
 */
export async function deployWithArtifacts(
  signer: ethers.Signer,
  artifact: { abi: unknown[]; bytecode: string },
  options: DeployOptions = {}
): Promise<DeploymentReceipt> {
  return deployContract(signer, artifact.abi, artifact.bytecode, options);
}
