// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
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
      // BUG: No timeout — fetch can hang indefinitely if the RPC node is unresponsive
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(request),
      });

      const json = await res.json();

      // BUG: Error response is not type-checked — json.error could have unexpected
      // shape and json.result is returned even when error is present
      if (json.error) {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }

      return json.result;
    }, this.retryOptions);
  }

  /**
   * Execute multiple JSON-RPC calls in a single batch request.
   * Responses are matched to requests by id field (not array order).
   * Individual failures return Error objects instead of throwing.
   * @param calls Array of method/params pairs
   * @param perRequestTimeoutMs Timeout per individual request in ms (default 30s)
   */
  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>,
    perRequestTimeoutMs: number = 30000
  ): Promise<unknown[]> {
    if (calls.length === 0) return [];

    // Build requests with stable IDs for matching
    const startId = this.requestId + 1;
    const requests: JsonRpcRequest[] = calls.map((c, i) => ({
      jsonrpc: "2.0" as const,
      id: startId + i,
      method: c.method,
      params: c.params,
    }));
    this.requestId = startId + calls.length - 1;

    // Create a map for O(1) response lookup by id
    const resultMap = new Map<number, unknown>();
    const errorMap = new Map<number, Error>();

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), perRequestTimeoutMs * calls.length);

      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!res.ok) {
        throw new Error(`Batch RPC HTTP error: ${res.status} ${res.statusText}`);
      }

      const responses: JsonRpcResponse[] = await res.json();

      // Match responses to requests by id, not array position
      for (const resp of responses) {
        if (resp.error) {
          errorMap.set(resp.id, new Error(`RPC error ${resp.error.code}: ${resp.error.message}`));
        } else {
          resultMap.set(resp.id, resp.result);
        }
      }
    } catch (err) {
      // If the entire batch fails (network/timeout), mark all as errors
      const batchError = err instanceof Error ? err : new Error(String(err));
      for (const req of requests) {
        if (!resultMap.has(req.id) && !errorMap.has(req.id)) {
          errorMap.set(req.id, batchError);
        }
      }
    }

    // Return results in original request order, with Errors for failures
    return requests.map((req) => {
      if (errorMap.has(req.id)) {
        return errorMap.get(req.id);
      }
      if (resultMap.has(req.id)) {
        return resultMap.get(req.id);
      }
      // Response missing entirely for this id
      return new Error(`RPC batch: no response for request id ${req.id}`);
    });
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
