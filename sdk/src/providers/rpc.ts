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

/**
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-24
 * @fixes #160 — Batch response matching by id, partial failure handling, timeout, batch limit
 */

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private static readonly MAX_BATCH_SIZE = 100;

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
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // 30s timeout

      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(request),
          signal: controller.signal,
        });
        clearTimeout(timeoutId);

        const json: JsonRpcResponse = await res.json();

        if (json.error) {
          throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
        }
        if (json.id !== request.id) {
          throw new Error("Response ID mismatch");
        }

        return json.result;
      } catch (e) {
        clearTimeout(timeoutId);
        throw e;
      }
    }, this.retryOptions);
  }

  /**
   * Execute batch RPC calls. Responses are matched by id (not sorted),
   * and partial failures are reported rather than silently dropping results.
   */
  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<(unknown | Error)[]> {
    // Limit batch size to prevent node overload
    const limited = calls.slice(0, RpcProvider.MAX_BATCH_SIZE);
    if (limited.length !== calls.length) {
      console.warn(`Batch call limited to ${RpcProvider.MAX_BATCH_SIZE} (requested ${calls.length})`);
    }

    const requests: JsonRpcRequest[] = limited.map((c) => ({
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

    // Build a map of id -> response for O(1) matching
    const responseMap = new Map<number, JsonRpcResponse>();
    for (const resp of responses) {
      responseMap.set(resp.id, resp);
    }

    // Match responses to requests by id (not sort!)
    const results: (unknown | Error)[] = [];
    for (const req of requests) {
      const resp = responseMap.get(req.id);
      if (!resp) {
        results.push(new Error(`No response for request id ${req.id}`));
        continue;
      }
      if (resp.error) {
        results.push(new Error(`RPC error for ${req.method}: ${resp.error.message}`));
      } else {
        results.push(resp.result);
      }
    }

    return results;
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
