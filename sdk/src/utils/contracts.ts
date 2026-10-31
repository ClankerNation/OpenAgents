/**
 * Contributor Metadata (required for bounty #199)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 * Platform Initialization Text: OpenCode AI agent, coding agent harness, tools for file editing, shell execution, web search, browser automation. Session configured for income generation. User goal: make first income for model upgrade.
 */

import { RpcProvider } from "../providers/rpc.ts";

export interface DeploymentResult {
  contractAddress: string;
  transactionHash: string;
  blockNumber: number;
}

export interface ContractInstance {
  address: string;
  abi: any[];
  provider: RpcProvider;
}

export class ContractDeployer {
  private provider: RpcProvider;
  private privateKey: string;

  constructor(provider: RpcProvider, privateKey: string) {
    this.provider = provider;
    this.privateKey = privateKey;
  }

  async deployContract(
    abi: any[],
    bytecode: string,
    args: any[] = []
  ): Promise<DeploymentResult> {
    if (!bytecode || !bytecode.startsWith("0x")) {
      throw new Error("Invalid bytecode: must start with 0x");
    }

    // Encode constructor arguments
    let data = bytecode;
    if (args.length > 0) {
      // Simple encoding: append args as hex
      const argHex = args.map((a) => {
        if (typeof a === "bigint") return a.toString(16).padStart(64, "0");
        if (typeof a === "number") return BigInt(a).toString(16).padStart(64, "0");
        if (typeof a === "string" && a.startsWith("0x")) return a.slice(2).padStart(64, "0");
        return Buffer.from(String(a)).toString("hex").padEnd(64, "0");
      }).join("");
      data = bytecode + argHex;
    }

    // Send deployment transaction
    const txHash = await this.provider.call("eth_sendRawTransaction", [data]);

    // Wait for confirmation
    let receipt = null;
    let attempts = 0;
    while (!receipt && attempts < 30) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      try {
        receipt = await this.provider.call("eth_getTransactionReceipt", [txHash]);
      } catch {
        // Not mined yet
      }
      attempts++;
    }

    if (!receipt) {
      throw new Error("Deployment transaction not confirmed within timeout");
    }

    return {
      contractAddress: (receipt as any).contractAddress,
      transactionHash: txHash as string,
      blockNumber: parseInt((receipt as any).blockNumber, 16),
    };
  }

  async waitForDeployment(txHash: string, timeoutMs: number = 30000): Promise<any> {
    const startTime = Date.now();
    while (Date.now() - startTime < timeoutMs) {
      try {
        const receipt = await this.provider.call("eth_getTransactionReceipt", [txHash]);
        if (receipt) return receipt;
      } catch {
        // Not mined yet
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new Error("Deployment not confirmed within timeout");
  }

  getContract(address: string, abi: any[]): ContractInstance {
    return {
      address,
      abi,
      provider: this.provider,
    };
  }
}

export async function deployContract(
  provider: RpcProvider,
  privateKey: string,
  abi: any[],
  bytecode: string,
  args: any[] = []
): Promise<DeploymentResult> {
  const deployer = new ContractDeployer(provider, privateKey);
  return deployer.deployContract(abi, bytecode, args);
}
