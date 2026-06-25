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
  /** Max batch size per call (default 100) */
  maxBatchSize?: number;
  /** Per-request timeout in ms (default 30000) */
  requestTimeout?: number;
}

/** Default max batch size to prevent node OOM */
const DEFAULT_MAX_BATCH_SIZE = 100;
/** Default per-request timeout */
const DEFAULT_REQUEST_TIMEOUT = 30000;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private maxBatchSize: number;
  private requestTimeout: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.maxBatchSize = config.maxBatchSize ?? DEFAULT_MAX_BATCH_SIZE;
    this.requestTimeout = config.requestTimeout ?? DEFAULT_REQUEST_TIMEOUT;
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      // FIX: AbortController for per-request timeout
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), this.requestTimeout);

      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(request),
          signal: controller.signal,
        });

        clearTimeout(timeout);

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        const json: JsonRpcResponse = await res.json();

        // FIX: Validate response structure — check id matches request
        if (json.id !== request.id) {
          throw new Error(`Response id mismatch: expected ${request.id}, got ${json.id}`);
        }

        // FIX: Properly handle error responses
        if (json.error) {
          const errMsg = json.error.message || "Unknown RPC error";
          throw new Error(`RPC error ${json.error.code || -1}: ${errMsg}`);
        }

        return json.result;
      } catch (err: unknown) {
        clearTimeout(timeout);
        if (err instanceof Error && err.name === "AbortError") {
          throw new Error(`Request timeout after ${this.requestTimeout}ms`);
        }
        throw err;
      }
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    // FIX: Enforce max batch size limit
    const chunks: Array<{ method: string; params: unknown[] }> = [];
    for (let i = 0; i < calls.length; i += this.maxBatchSize) {
      chunks.push(calls.slice(i, i + this.maxBatchSize));
    }

    const results: unknown[] = [];

    for (const chunk of chunks) {
      const responses = await this._sendBatch(chunk);
      results.push(...responses);
    }

    return results;
  }

  /**
   * Send a batch of JSON-RPC requests and match responses by id.
   * FIX: Each request gets a unique id; responses are matched by id, not position.
   * Partial failures (some errors) are preserved rather than failing the entire batch.
   */
  private async _sendBatch(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    // Assign unique ids to each request
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // FIX: AbortController for batch timeout
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.requestTimeout * calls.length);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const rawResponses: unknown[] = await res.json();

      if (!Array.isArray(rawResponses)) {
        // Some nodes return a single result for non-batch requests
        return [rawResponses];
      }

      // FIX: Build a map of id -> response for O(1) lookup
      const responseMap = new Map<number, JsonRpcResponse>();
      for (const resp of rawResponses) {
        if (resp && typeof resp === "object" && "id" in resp && "jsonrpc" in resp) {
          const r = resp as JsonRpcResponse;
          responseMap.set(r.id, r);
        }
      }

      // FIX: Match responses to requests by id, not by sort order
      // This handles out-of-order responses per JSON-RPC spec
      const results: unknown[] = [];
      for (const req of requests) {
        const resp = responseMap.get(req.id);
        if (!resp) {
          // Response not found — request may have timed out on the node
          results.push(null);
          continue;
        }

        if (resp.error) {
          // FIX: Preserve individual errors instead of throwing the whole batch
          results.push({ error: true, code: resp.error.code, message: resp.error.message });
        } else {
          results.push(resp.result ?? null);
        }
      }

      return results;
    } catch (err: unknown) {
      clearTimeout(timeout);
      if (err instanceof Error && err.name === "AbortError") {
        throw new Error(`Batch request timeout after ${this.requestTimeout * calls.length}ms`);
      }
      throw err;
    }
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
