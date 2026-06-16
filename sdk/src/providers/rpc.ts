import { withRetry, RetryOptions } from "../utils/retry";

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: unknown[];
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
}

export interface DeploymentReceipt {
  address: string;
  txHash: string;
  gasUsed: bigint;
  blockNumber: number;
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(request),
      });

      const json = await res.json();

      if (json.error) {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }

      return json.result;
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const res = await fetch(this.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.headers },
      body: JSON.stringify(requests),
    });

    const responses: JsonRpcResponse[] = await res.json();
    return responses
      .sort((a, b) => a.id - b.id)
      .map((r) => r.result);
  }

  async getBlockNumber(): Promise<number> {
    const hex = (await this.call("eth_blockNumber")) as string;
    return parseInt(hex, 16);
  }

  async getBalance(address: string): Promise<bigint> {
    const hex = (await this.call("eth_getBalance", [address, "latest"])) as string;
    return BigInt(hex);
  }

  getChainId(): number {
    return this.chainId;
  }

  /**
   * Deploys a contract to the network.
   * @param bytecode The compiled bytecode of the contract.
   * @param args Encoded constructor arguments.
   * @param from The address deploying the contract.
   * @param confirmations Number of block confirmations to wait for.
   * @returns A deployment receipt.
   */
  async deployContract(
    bytecode: string, 
    args: string = "0x", 
    from: string, 
    confirmations: number = 1
  ): Promise<DeploymentReceipt> {
    const data = bytecode + args;
    
    // Use eth_sendTransaction (assuming a node with an unlocked account for simplicity, 
    // or that the user is using a provider that handles signing)
    const txHash = (await this.call("eth_sendTransaction", [{
      from,
      data,
      gas: "0x500000", // Default gas limit
    }])) as string;

    // Wait for confirmation
    let receipt = null;
    let attempts = 0;
    while (!receipt && attempts < 60) {
      receipt = await this.call("eth_getTransactionReceipt", [txHash]);
      if (!receipt) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        attempts++;
      }
    }

    if (!receipt) {
      throw new Error("Contract deployment timed out");
    }

    // Wait for additional confirmations
    const startBlock = receipt.blockNumber;
    let currentBlock = 0;
    while (currentBlock < confirmations) {
      currentBlock = (await this.getBlockNumber()) - startBlock;
      if (currentBlock < confirmations) {
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    }

    return {
      address: receipt.contractAddress,
      txHash: txHash,
      gasUsed: BigInt(receipt.gasUsed),
      blockNumber: receipt.blockNumber,
    };
  }
}
