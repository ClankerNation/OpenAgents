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
  batchTimeoutMs?: number;
  individualTimeoutMs?: number;
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private batchTimeoutMs: number;
  private individualTimeoutMs: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.batchTimeoutMs = config.batchTimeoutMs ?? 30000;
    this.individualTimeoutMs = config.individualTimeoutMs ?? 10000;
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
      const timeout = setTimeout(() => controller.abort(), this.individualTimeoutMs);

      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(request),
          signal: controller.signal,
        });

        const json = (await res.json()) as JsonRpcResponse;

        if (json.error) {
          throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
        }

        return json.result;
      } finally {
        clearTimeout(timeout);
      }
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    if (calls.length === 0) return [];

    // Build requests with unique IDs and track mapping
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // Create ID-to-index map for response matching
    const idToIndex = new Map<number, number>();
    for (let i = 0; i < requests.length; i++) {
      idToIndex.set(requests[i].id, i);
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.batchTimeoutMs);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      const responses: JsonRpcResponse[] = await res.json();

      // Initialize results array with null placeholders
      const results: unknown[] = new Array(calls.length).fill(null);
      const errors: Array<{ index: number; error: string }> = [];

      // Match responses to requests by ID (handles out-of-order responses)
      for (const response of responses) {
        const index = idToIndex.get(response.id);
        if (index === undefined) {
          // Response with unknown ID — skip
          continue;
        }

        if (response.error) {
          // Individual failure doesn't fail the entire batch
          errors.push({
            index,
            error: `RPC error ${response.error.code}: ${response.error.message}`,
          });
          results[index] = null;
        } else {
          results[index] = response.result;
        }
      }

      // Check for missing responses (timed-out individual requests)
      const respondedIds = new Set(responses.map((r) => r.id));
      for (let i = 0; i < requests.length; i++) {
        if (!respondedIds.has(requests[i].id)) {
          errors.push({
            index: i,
            error: "Individual request timed out or missing from batch response",
          });
          results[i] = null;
        }
      }

      // If all requests failed, throw aggregate error
      if (errors.length === calls.length) {
        throw new Error(
          `All ${calls.length} batch requests failed: ${errors.map((e) => `[${e.index}] ${e.error}`).join("; ")}`
        );
      }

      return results;
    } finally {
      clearTimeout(timeout);
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
