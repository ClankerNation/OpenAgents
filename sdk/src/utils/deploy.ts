// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

import { Wallet } from "../auth/wallet";
import { encodeParams, AbiParam } from "./encoding";
import { RpcProvider } from "../providers/rpc";

export interface DeploymentReceipt {
  contractAddress: string;
  transactionHash: string;
  blockNumber: number;
  gasUsed: bigint;
  deployer: string;
}

export interface DeployOptions {
  /** Number of block confirmations to wait for after deployment */
  confirmations?: number;
  /** Gas limit override for deployment transaction */
  gasLimit?: bigint;
  /** Max fee per gas for EIP-1559 transactions */
  maxFeePerGas?: bigint;
  /** Max priority fee per gas for EIP-1559 transactions */
  maxPriorityFeePerGas?: bigint;
  /** Legacy gas price (if set, uses legacy tx instead of EIP-1559) */
  gasPrice?: bigint;
}

/**
 * Deploy a smart contract and wait for confirmation.
 * @param wallet Wallet instance to sign the deployment transaction
 * @param bytecode Contract bytecode (hex string with 0x prefix)
 * @param abi Constructor ABI parameters for encoding args
 * @param args Constructor argument values matching the ABI
 * @param options Deployment options (confirmations, gas settings)
 * @returns Deployment receipt with address, tx hash, block number, and gas used
 */
export async function deployContract(
  wallet: Wallet,
  bytecode: string,
  abi: AbiParam[],
  args: unknown[] = [],
  options: DeployOptions = {}
): Promise<DeploymentReceipt> {
  const confirmations = options.confirmations ?? 1;

  // Encode constructor arguments and append to bytecode
  let deployData = bytecode;
  if (abi.length > 0 && args.length > 0) {
    if (abi.length !== args.length) {
      throw new Error(
        `Constructor arg count mismatch: expected ${abi.length}, got ${args.length}`
      );
    }
    const encodedArgs = encodeParams(
      abi.map((param, i) => ({
        type: param.type,
        value: args[i] as string | number | bigint | boolean,
      }))
    );
    // Append encoded args to bytecode (without 0x prefix on encodedArgs)
    deployData = bytecode + encodedArgs.slice(2);
  }

  // Send deployment transaction (to: null for contract creation)
  const txHash = await wallet.sendTransaction({
    to: "0x0000000000000000000000000000000000000000",
    value: 0n,
    data: deployData,
    gasLimit: options.gasLimit ?? 3_000_000n,
    gasPrice: options.gasPrice,
    maxFeePerGas: options.maxFeePerGas,
    maxPriorityFeePerGas: options.maxPriorityFeePerGas,
  });

  // Wait for transaction receipt with confirmations
  const provider = (wallet as any).provider as RpcProvider;
  let receipt: any = null;
  let attempts = 0;
  const maxAttempts = 120; // ~2 minutes at 1s polling

  while (!receipt && attempts < maxAttempts) {
    try {
      receipt = await provider.call("eth_getTransactionReceipt", [txHash]);
    } catch {
      // Receipt not available yet
    }
    if (!receipt) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      attempts++;
    }
  }

  if (!receipt) {
    throw new Error(`Deployment transaction ${txHash} not confirmed after ${maxAttempts}s`);
  }

  // Wait for additional confirmations if requested
  if (confirmations > 1) {
    const deployBlock = parseInt(receipt.blockNumber, 16);
    let currentBlock = deployBlock;
    while (currentBlock - deployBlock + 1 < confirmations) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const hex = (await provider.call("eth_blockNumber")) as string;
      currentBlock = parseInt(hex, 16);
    }
  }

  if (!receipt.contractAddress) {
    throw new Error("Deployment failed: no contract address in receipt");
  }

  return {
    contractAddress: receipt.contractAddress,
    transactionHash: txHash,
    blockNumber: parseInt(receipt.blockNumber, 16),
    gasUsed: BigInt(receipt.gasUsed),
    deployer: wallet.address,
  };
}
