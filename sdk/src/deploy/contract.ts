/**
 * @fix-author kejuunuy
 * Contract deployment helpers for OpenAgents SDK.
 * Provides deployContract with constructor args support, gas estimation, and deployment confirmation.
 */

import { ethers } from "ethers";

export interface DeployContractOptions {
  /** Compiled contract bytecode (hex string starting with 0x) */
  bytecode: string;
  /** ABI fragment for the constructor (only the constructor entry needed) */
  abi: ethers.InterfaceAbi;
  /** Constructor arguments to encode */
  constructorArgs?: unknown[];
  /** Custom gas limit (skips estimation if provided) */
  gasLimit?: bigint;
  /** Gas price in wei (if omitted, fetched from provider) */
  gasPrice?: bigint;
  /** Value to send with deployment transaction (in wei) */
  value?: bigint;
  /** Number of confirmations to wait for (default: 1) */
  confirmations?: number;
  /** Timeout in ms to wait for deployment receipt (default: 120000) */
  timeout?: number;
}

export interface DeploymentResult {
  /** Address of the deployed contract */
  contractAddress: string;
  /** Transaction hash of the deployment */
  transactionHash: string;
  /** Block number in which the contract was deployed */
  blockNumber: number;
  /** Gas actually used */
  gasUsed: bigint;
  /** Effective gas price paid */
  effectiveGasPrice: bigint;
  /** The deployment receipt */
  receipt: ethers.TransactionReceipt;
  /** Contract instance connected to the signer */
  contract: ethers.Contract;
}

/**
 * Estimates the gas required to deploy a contract.
 */
export async function estimateDeployGas(
  signer: ethers.Wallet,
  bytecode: string,
  abi: ethers.InterfaceAbi,
  constructorArgs: unknown[] = [],
  value: bigint = 0n
): Promise<bigint> {
  const factory = new ethers.ContractFactory(abi, bytecode, signer);
  const deployTx = await factory.getDeployTransaction(...constructorArgs);
  const gasEstimate = await signer.estimateGas({
    ...deployTx,
    value,
  });
  // Add 20% buffer for safety
  return (gasEstimate * 120n) / 100n;
}

/**
 * Deploys a contract and waits for confirmation.
 */
export async function deployContract(
  signer: ethers.Wallet,
  options: DeployContractOptions
): Promise<DeploymentResult> {
  const {
    bytecode,
    abi,
    constructorArgs = [],
    gasLimit,
    gasPrice,
    value = 0n,
    confirmations = 1,
    timeout = 120_000,
  } = options;

  if (!bytecode || bytecode === "0x") {
    throw new Error("DeployContractError: bytecode is empty or invalid");
  }

  const factory = new ethers.ContractFactory(abi, bytecode, signer);
  const deployTx = await factory.getDeployTransaction(...constructorArgs);

  // Estimate gas if not provided
  const estimatedGasLimit = gasLimit ?? await estimateDeployGas(
    signer, bytecode, abi, constructorArgs, value
  );

  // Get gas price if not provided
  const resolvedGasPrice = gasPrice ?? (await signer.provider!.getFeeData()).gasPrice!;

  // Send deployment transaction
  const tx = await signer.sendTransaction({
    ...deployTx,
    value,
    gasLimit: estimatedGasLimit,
    gasPrice: resolvedGasPrice,
  });

  // Wait for confirmations with timeout
  const receipt = await Promise.race([
    tx.wait(confirmations),
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`DeployContractError: deployment timed out after ${timeout}ms`)), timeout)
    ),
  ]);

  if (!receipt) {
    throw new Error("DeployContractError: deployment failed — no receipt returned");
  }

  if (receipt.status === 0) {
    throw new Error("DeployContractError: deployment transaction reverted");
  }

  const contractAddress = receipt.contractAddress;
  if (!contractAddress) {
    throw new Error("DeployContractError: no contract address in receipt");
  }

  const contract = new ethers.Contract(contractAddress, abi, signer);

  return {
    contractAddress,
    transactionHash: receipt.hash,
    blockNumber: receipt.blockNumber,
    gasUsed: receipt.gasPrice ? receipt.gasPrice : 0n,
    effectiveGasPrice: receipt.gasPrice ?? 0n,
    receipt,
    contract,
  };
}
