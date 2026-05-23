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

export interface BatchResult {
  results: Map<number, unknown>;
  errors: Map<number, Error>;
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  batchTimeoutMs?: number;
  maxBatchSize?: number;
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private batchTimeoutMs: number;
  private maxBatchSize: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.batchTimeoutMs = config.batchTimeoutMs ?? 30000;
    this.maxBatchSize = config.maxBatchSize ?? 100;
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.batchTimeoutMs);
      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          signal: controller.signal,
          body: JSON.stringify(request),
        });

        const json = await res.json();

        if (json.error) {
          throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
        }

        return json.result;
      } finally {
        clearTimeout(timeoutId);
      }
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<BatchResult> {
    const chunks: Array<Array<{ method: string; params: unknown[] }>> = [];
    for (let i = 0; i < calls.length; i += this.maxBatchSize) {
      chunks.push(calls.slice(i, i + this.maxBatchSize));
    }

    const allResults = new Map<number, unknown>();
    const allErrors = new Map<number, Error>();

    for (const chunk of chunks) {
      const requests: JsonRpcRequest[] = chunk.map((c) => ({
        jsonrpc: "2.0" as const,
        id: ++this.requestId,
        method: c.method,
        params: c.params,
      }));

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.batchTimeoutMs);

      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          signal: controller.signal,
          body: JSON.stringify(requests),
        });

        const responses: JsonRpcResponse[] = await res.json();
        const idToRequest = new Map(requests.map((r) => [r.id, r]));

        for (const response of responses) {
          if (!idToRequest.has(response.id)) continue;
          if (response.error) {
            allErrors.set(response.id, new Error(`RPC error ${response.error.code}: ${response.error.message}`));
          } else {
            allResults.set(response.id, response.result);
          }
        }

        for (const req of requests) {
          if (!allResults.has(req.id) && !allErrors.has(req.id)) {
            allErrors.set(req.id, new Error("RPC timeout: no response received for request"));
          }
        }
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        for (const req of requests) {
          allErrors.set(req.id, error);
        }
      } finally {
        clearTimeout(timeoutId);
      }
    }

    return { results: allResults, errors: allErrors };
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
}
