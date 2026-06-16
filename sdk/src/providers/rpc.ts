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

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private simulationCache = new Map<string, { block: number; result: any }>();

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

  async simulateTransaction(txParams: any): Promise<{ success: boolean; reason?: string }> {
    const blockNumber = await this.getBlockNumber();
    const cacheKey = JSON.stringify(txParams);
    const cached = this.simulationCache.get(cacheKey);

    if (cached && cached.block === blockNumber) {
      return { success: cached.result.success, reason: cached.result.reason };
    }

    try {
      // eth_call simulates the transaction
      await this.call("eth_call", [txParams, "latest"]);
      
      const result = { success: true };
      this.simulationCache.set(cacheKey, { block: blockNumber, result });
      return result;
    } catch (error: any) {
      const reason = error.message || "Transaction reverted";
      const result = { success: false, reason };
      this.simulationCache.set(cacheKey, { block: blockNumber, result });
      return result;
    }
  }
}
