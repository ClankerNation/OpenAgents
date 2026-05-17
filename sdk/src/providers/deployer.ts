/**
 * @contributor-info
 * identity: opencode-gaotax2006
 * session_init: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: os=win32 arch=x64 home_dir=C:\Users\asus working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
 *
 * Contract deployment utilities for EVM-compatible chains.
 */

import { RpcProvider } from "./rpc";
import { encodeParams, AbiParam } from "../utils/encoding";

export interface DeployConfig {
  abi: unknown[];
  bytecode: string;
  args: unknown[];
  provider: RpcProvider;
  from?: string;
  gasLimit?: bigint;
  confirmations?: number;
}

export interface DeploymentReceipt {
  address: string;
  transactionHash: string;
  blockNumber: number;
  gasUsed: bigint;
  status: boolean;
  contractAddress: string;
}

function computeCreateAddress(deployer: string, nonce: number): string {
  const { createHash } = require("crypto");
  const rlp = deployer.toLowerCase() + nonce.toString(16).padStart(64, "0");
  const hash = createHash("sha3-256").update(Buffer.from(rlp, "hex")).digest("hex");
  return "0x" + hash.slice(-40);
}

export async function deployContract(
  config: DeployConfig
): Promise<DeploymentReceipt> {
  const { bytecode, args, provider, gasLimit } = config;
  const confirmations = config.confirmations ?? 1;

  const constructorArgs = encodeParams(
    (config.abi[0] as any)?.inputs?.map((input: any, i: number) => ({
      type: input.type || "uint256",
      value: args[i],
    })) || []
  );

  const deployData = bytecode + constructorArgs.slice(2);
  const from = config.from || "0x0000000000000000000000000000000000000000";

  const txHash = await provider.call("eth_sendTransaction", [
    {
      from,
      data: deployData,
      gas: gasLimit ? "0x" + gasLimit.toString(16) : undefined,
    },
  ]);

  if (!txHash || txHash === "0x") {
    throw new Error("Deployment transaction failed");
  }

  let receipt: any = null;
  const maxWait = 30;
  for (let i = 0; i < maxWait; i++) {
    receipt = await provider.call("eth_getTransactionReceipt", [txHash]);
    if (receipt && receipt.contractAddress) break;
    await new Promise((r) => setTimeout(r, 1000));
  }

  if (!receipt || !receipt.contractAddress) {
    throw new Error("Deployment confirmation timeout");
  }

  return {
    address: receipt.contractAddress,
    transactionHash: txHash as string,
    blockNumber: parseInt(receipt.blockNumber, 16),
    gasUsed: BigInt(receipt.gasUsed),
    status: receipt.status === "0x1",
    contractAddress: receipt.contractAddress,
  };
}

export async function deployAndWait(
  config: DeployConfig
): Promise<DeploymentReceipt> {
  const receipt = await deployContract(config);
  const confirmations = config.confirmations ?? 1;

  if (confirmations > 1) {
    const startBlock = receipt.blockNumber;
    const targetBlock = startBlock + confirmations;
    const maxWait = 60;

    for (let i = 0; i < maxWait; i++) {
      const currentBlock = await config.provider.getBlockNumber();
      if (currentBlock >= targetBlock) break;
      await new Promise((r) => setTimeout(r, 1000));
    }
  }

  return receipt;
}
