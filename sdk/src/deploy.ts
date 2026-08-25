/**
 * @contributor-info rafaio1
 * @session-init Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for contract deployment helpers (Issue #186)
 * @os linux
 * @arch x64
 * @home /root
 * @workdir /tmp/openagents_issue_186
 * @shell /bin/bash
 */
import { ethers } from "ethers";

/** Immutable deployment receipt containing all on-chain metadata. */
export interface DeploymentReceipt {
  readonly address: string;
  readonly transactionHash: string;
  readonly gasUsed: bigint;
  readonly blockNumber: number;
  readonly constructorArgs: unknown[];
}

/** Configuration options for contract deployment. */
export interface DeployOptions {
  /** Number of block confirmations to wait after deployment tx is mined. Default: 1 */
  confirmations?: number;
  /** Gas limit override for the deployment transaction. */
  gasLimit?: bigint;
  /** Value in wei to send with the deployment (for payable constructors). */
  value?: bigint;
}

/**
 * Deploys a smart contract and waits for on-chain confirmation.
 *
 * @param signer - Authenticated ethers Signer with provider connection
 * @param abi - Contract ABI (human-readable or JSON format)
 * @param bytecode - Compiled contract bytecode (hex string)
 * @param args - Constructor arguments matching the ABI constructor signature
 * @param options - Optional deployment configuration
 * @returns Immutable DeploymentReceipt with address, tx hash, gas, and block number
 */
export async function deployContract(
  signer: ethers.Signer,
  abi: ethers.InterfaceAbi,
  bytecode: string,
  args: unknown[] = [],
  options: DeployOptions = {},
): Promise<DeploymentReceipt> {
  const factory = new ethers.ContractFactory(abi, bytecode, signer);

  const overrides: ethers.Overrides = {};
  if (options.gasLimit !== undefined) {
    overrides.gasLimit = options.gasLimit;
  }
  if (options.value !== undefined) {
    overrides.value = options.value;
  }

  const contract = await factory.deploy(...args, overrides);
  const deployed = await contract.waitForDeployment();

  const deployTx = contract.deploymentTransaction();
  if (!deployTx) {
    throw new Error("Deployment transaction not available — contract may have failed silently");
  }

  const confirmations = options.confirmations ?? 1;
  const receipt = await deployTx.wait(confirmations);

  if (!receipt || !receipt.contractAddress) {
    throw new Error("Deployment failed: no contract address in transaction receipt");
  }

  return Object.freeze({
    address: receipt.contractAddress,
    transactionHash: receipt.hash,
    gasUsed: receipt.gasUsed,
    blockNumber: receipt.blockNumber,
    constructorArgs: [...args],
  });
}
